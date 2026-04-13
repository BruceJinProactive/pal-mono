"""Voice evaluation runner.

Orchestrates end-to-end voice eval for a single scenario using Option B
(direct room injection): create LiveKit room → inject synthetic caller →
run conversation turns via TTS → wait for completion → collect results.

Usage::

    from services.eval_service._voice_eval_runner import (
        VoiceEvalConfig,
        run_voice_scenario,
    )

    config = VoiceEvalConfig.from_env()
    record = await run_voice_scenario(scenario, config, session)
    results = await evaluate_scenario(record)

The synthetic caller (LiveKit RTC participant that publishes TTS audio and
captures agent responses) is injected via the ``caller_factory`` parameter.
This keeps the runner testable and decoupled from ``livekit-rtc``.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Protocol

from pal_agents.evals.voice.personas import resolve_persona
from pal_agents.evals.voice.room_orchestrator import (
    LiveKitRoomOrchestrator,
    RoomConfig,
    RoomInfo,
)
from pal_agents.evals.voice.tts_engine import TTSEngine, VoiceProfile
from sqlalchemy.ext.asyncio import AsyncSession

from services.eval_service._evaluators import ConversationRecord
from services.eval_service._voice_result_collector import (
    VoiceEvalResult,
    VoiceResultCollector,
)
from services.eval_service.schema import EvalScenario, TurnType, UserTurn
from utils.log import logger

_DEFAULT_CALL_TIMEOUT_S = 120.0
_DEFAULT_ROOM_EMPTY_TIMEOUT_S = 300


class SyntheticCallerFactory(Protocol):
    """Factory protocol for creating synthetic callers.

    Implementations connect to a LiveKit room as an RTC participant,
    publish TTS audio for each turn, and return the call_id assigned
    by the agent's end-call callback.
    """

    async def run_call(
        self,
        room_info: RoomInfo,
        caller_token: str,
        turns: list[str],
        voice_profile: VoiceProfile,
        tts_engine: TTSEngine,
    ) -> str:
        """Run a synthetic call in the given room.

        Args:
            room_info: LiveKit room to connect to.
            caller_token: JWT token for the synthetic caller participant.
            turns: List of user turn texts to speak.
            voice_profile: TTS voice configuration for this persona.
            tts_engine: TTS engine instance for speech synthesis.

        Returns:
            The call_id assigned to this conversation (used to collect results).
        """
        ...


@dataclass
class VoiceEvalConfig:
    """Configuration for voice evaluation runs.

    Holds credentials and settings needed to orchestrate voice eval calls.
    """

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    cartesia_api_key: str

    call_timeout_s: float = _DEFAULT_CALL_TIMEOUT_S
    room_empty_timeout_s: int = _DEFAULT_ROOM_EMPTY_TIMEOUT_S

    def __repr__(self) -> str:
        """Redact credentials from repr output."""
        return (
            f"VoiceEvalConfig(livekit_url={self.livekit_url!r}, "
            f"livekit_api_key='***', livekit_api_secret='***', "
            f"cartesia_api_key='***')"
        )

    @classmethod
    def from_env(cls) -> VoiceEvalConfig:
        """Create config from environment variables.

        Required env vars:
            LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CARTESIA_API_KEY

        Raises:
            ValueError: If any required env var is missing.
        """
        missing: list[str] = []
        livekit_url = os.environ.get("LIVEKIT_URL", "")
        livekit_api_key = os.environ.get("LIVEKIT_API_KEY", "")
        livekit_api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
        cartesia_api_key = os.environ.get("CARTESIA_API_KEY", "")

        if not livekit_url:
            missing.append("LIVEKIT_URL")
        if not livekit_api_key:
            missing.append("LIVEKIT_API_KEY")
        if not livekit_api_secret:
            missing.append("LIVEKIT_API_SECRET")
        if not cartesia_api_key:
            missing.append("CARTESIA_API_KEY")

        if missing:
            raise ValueError(
                f"Missing required environment variables for voice eval: {', '.join(missing)}"
            )

        return cls(
            livekit_url=livekit_url,
            livekit_api_key=livekit_api_key,
            livekit_api_secret=livekit_api_secret,
            cartesia_api_key=cartesia_api_key,
        )


def _extract_turn_texts(scenario: EvalScenario) -> list[str]:
    """Extract plain-text user turns from a scenario.

    AI-driven turns use their goal text as a placeholder since the
    voice caller speaks pre-synthesized audio (no live LLM generation).

    Args:
        scenario: The eval scenario.

    Returns:
        List of text strings to synthesize and speak.
    """
    texts: list[str] = []
    for turn in scenario.user_turns:
        if isinstance(turn, UserTurn):
            if turn.type == TurnType.AI_DRIVEN:
                text = turn.goal or turn.text or ""
            else:
                text = turn.text or ""
            texts.append(text)
        else:
            texts.append(str(turn))
    return [t for t in texts if t]


async def run_voice_scenario(
    scenario: EvalScenario,
    config: VoiceEvalConfig,
    session: AsyncSession,
    caller_factory: SyntheticCallerFactory | None = None,
) -> ConversationRecord:
    """Run a single voice eval scenario end-to-end.

    Orchestrates the full Option B flow:
        1. Resolve persona → VoiceProfile
        2. Create LiveKit room
        3. Generate participant tokens
        4. Run synthetic call (TTS turns → agent responds)
        5. Collect results from DB via VoiceResultCollector
        6. Convert to ConversationRecord for evaluators

    Args:
        scenario: The eval scenario to run.
        config: Voice eval configuration (credentials, timeouts).
        session: Database session for result collection.
        caller_factory: Factory for creating synthetic callers. If None,
            the call setup is performed but no audio is published (useful
            for integration testing the wiring without livekit-rtc).

    Returns:
        ConversationRecord ready for the evaluator pipeline.

    Raises:
        ValueError: If voice eval config is invalid.
        TimeoutError: If the call does not complete within the timeout.
    """
    voice_profile = resolve_persona(scenario.persona)
    turn_texts = _extract_turn_texts(scenario)

    orchestrator = LiveKitRoomOrchestrator(
        livekit_url=config.livekit_url,
        api_key=config.livekit_api_key,
        api_secret=config.livekit_api_secret,
    )
    tts_engine = TTSEngine(
        api_key=config.cartesia_api_key,
        default_profile=voice_profile,
    )

    created_room_name: str | None = None
    try:
        # 1. Create room
        room_config = RoomConfig(empty_timeout_s=config.room_empty_timeout_s)
        room_info = await orchestrator.create_room(room_config)
        created_room_name = room_info.room_name

        logger.info(
            "Voice eval room created",
            extra={
                "room_name": created_room_name,
                "scenario_id": scenario.scenario_id,
                "persona": scenario.persona,
            },
        )

        # 2. Generate tokens
        caller_token = orchestrator.generate_token(
            created_room_name,
            identity="eval-synthetic-caller",
            can_publish=True,
            can_subscribe=True,
        )
        # 3. Run synthetic call (bounded by call_timeout_s)
        if caller_factory is not None:
            call_id = await asyncio.wait_for(
                caller_factory.run_call(
                    room_info=room_info,
                    caller_token=caller_token.token,
                    turns=turn_texts,
                    voice_profile=voice_profile,
                    tts_engine=tts_engine,
                ),
                timeout=config.call_timeout_s,
            )
        else:
            # No caller factory — return empty record for wiring tests.
            # In production, a SyntheticCaller implementation is required.
            logger.warning(
                "No caller_factory provided — voice eval room created but "
                "no synthetic call placed. Returning empty ConversationRecord.",
                extra={
                    "room_name": created_room_name,
                    "scenario_id": scenario.scenario_id,
                },
            )
            return ConversationRecord(scenario=scenario)

        # 4. Collect results
        assert isinstance(created_room_name, str)
        room_name = created_room_name
        collector = VoiceResultCollector(session)
        voice_result: VoiceEvalResult = await collector.collect(
            call_id=call_id,
            room_name=room_name,
            timeout_s=config.call_timeout_s,
        )

        logger.info(
            "Voice eval results collected",
            extra={
                "call_id": call_id,
                "room_name": created_room_name,
                "transcript_length": len(voice_result.transcript),
                "duration_s": voice_result.metrics.duration_seconds,
            },
        )

        # 5. Convert to ConversationRecord
        return voice_result.to_conversation_record(scenario)

    finally:
        # Best-effort cleanup — each step is isolated so one failure
        # does not prevent the others from running.
        if created_room_name is not None:
            try:
                await orchestrator.teardown(created_room_name)
            except Exception:
                logger.exception("Failed to teardown room %s", created_room_name)
        try:
            await orchestrator.close()
        except Exception:
            logger.exception("Failed to close orchestrator")
        try:
            await tts_engine.close()
        except Exception:
            logger.exception("Failed to close TTS engine")
