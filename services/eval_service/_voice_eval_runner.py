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
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from pal_agents.evals.voice.personas import resolve_persona
from pal_agents.evals.voice.room_orchestrator import (
    LiveKitRoomOrchestrator,
    ParticipantToken,
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
from utils.secret import get_server_secret_with_fallback

_DEFAULT_CALL_TIMEOUT_S = 120.0
_DEFAULT_ROOM_EMPTY_TIMEOUT_S = 300
_EGRESS_POLL_INTERVAL_S = 3.0
_EGRESS_POLL_TIMEOUT_S = 60.0


class SyntheticCallerFactory(Protocol):
    """Factory protocol for creating synthetic callers.

    Implementations connect to a LiveKit room as an RTC participant,
    publish TTS audio for each turn, and return the call_id used
    to collect results from the database.
    """

    async def run_call(
        self,
        room_info: RoomInfo,
        caller_token: str,
        turns: list[str],
        voice_profile: VoiceProfile,
        tts_engine: TTSEngine,
        call_id: str,
    ) -> str:
        """Run a synthetic call in the given room.

        Args:
            room_info: LiveKit room to connect to.
            caller_token: JWT token for the synthetic caller participant.
                The token includes ``sip.callID`` in participant attributes
                so the agent can read it.
            turns: List of user turn texts to speak.
            voice_profile: TTS voice configuration for this persona.
            tts_engine: TTS engine instance for speech synthesis.
            call_id: Pre-generated call ID embedded in the caller token.

        Returns:
            The call_id (same as input, for protocol consistency).
        """
        ...


@dataclass
class VoiceEvalConfig:
    """Configuration for voice evaluation runs.

    Holds credentials and settings needed to orchestrate voice eval calls.

    When ``recording_s3_bucket`` is set, a Room Composite Egress is started
    for each eval call to record the full room audio to S3.  The resulting
    S3 URI is passed to the evaluator pipeline so audio-based evaluators
    (E16 STT accuracy, E17b audio quality) can access the recording.
    """

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    cartesia_api_key: str

    call_timeout_s: float = _DEFAULT_CALL_TIMEOUT_S
    room_empty_timeout_s: int = _DEFAULT_ROOM_EMPTY_TIMEOUT_S

    # LiveKit agent name for explicit dispatch into eval rooms.
    agent_name: str = "palona-voice"

    # Optional S3 recording config — leave bucket empty to skip recording.
    recording_s3_bucket: str = ""
    recording_s3_region: str = "us-east-1"

    def __repr__(self) -> str:
        """Redact credentials from repr output."""
        return (
            f"VoiceEvalConfig(livekit_url={self.livekit_url!r}, "
            f"livekit_api_key='***', livekit_api_secret='***', "
            f"cartesia_api_key='***', "
            f"recording_s3_bucket={self.recording_s3_bucket!r})"
        )

    @classmethod
    def from_env(cls) -> VoiceEvalConfig:
        """Create config from environment variables.

        Required env vars:
            LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET,
            CARTESIA_VOICE_EVAL_API_KEY

        Optional env vars:
            VOICE_EVAL_RECORDING_BUCKET — S3 bucket for call recordings.
                When set, AWS credentials must be available to the LiveKit
                egress service (via IAM role or ``AWS_ACCESS_KEY_ID`` /
                ``AWS_SECRET_ACCESS_KEY`` environment variables).
            VOICE_EVAL_RECORDING_REGION — AWS region (default ``us-east-1``).

        Raises:
            ValueError: If any required secret is missing from both
                AWS Secrets Manager and environment variables.
        """
        missing: list[str] = []

        def _get(key: str) -> str:
            try:
                return get_server_secret_with_fallback(key)
            except ValueError:
                missing.append(key)
                return ""

        livekit_url = _get("LIVEKIT_URL")
        livekit_api_key = _get("LIVEKIT_API_KEY")
        livekit_api_secret = _get("LIVEKIT_API_SECRET")
        cartesia_api_key = _get("CARTESIA_VOICE_EVAL_API_KEY")

        if missing:
            raise ValueError(
                f"Missing required secrets for voice eval: {', '.join(missing)}"
            )

        return cls(
            livekit_url=livekit_url,
            livekit_api_key=livekit_api_key,
            livekit_api_secret=livekit_api_secret,
            cartesia_api_key=cartesia_api_key,
            recording_s3_bucket=os.environ.get("VOICE_EVAL_RECORDING_BUCKET", ""),
            recording_s3_region=os.environ.get(
                "VOICE_EVAL_RECORDING_REGION", "us-east-1"
            ),
        )


def _generate_caller_token(
    orchestrator: LiveKitRoomOrchestrator,
    room_name: str,
    call_id: str,
    dialed_number: str = "",
) -> ParticipantToken:
    """Generate a participant token with SIP-compatible attributes.

    The LiveKit agent reads ``participant.attributes["sip.callID"]`` to
    identify calls, and ``sip.phoneNumber`` / ``sip.trunkPhoneNumber``
    to resolve the project via the pal-mono init endpoint.

    For eval calls there is no SIP bridge, so we embed these values
    in the JWT attributes directly.
    """
    from datetime import timedelta

    from livekit.api import AccessToken, VideoGrants

    attrs: dict[str, str] = {"sip.callID": call_id}
    normalized = dialed_number.strip()
    if normalized:
        # sip.phoneNumber = caller's number (synthetic caller)
        # sip.trunkPhoneNumber = dialed number (project's phone number)
        attrs["sip.phoneNumber"] = "+10000000000"
        attrs["sip.trunkPhoneNumber"] = normalized

    token = (
        AccessToken(orchestrator.api_key, orchestrator.api_secret)
        .with_identity("eval-synthetic-caller")
        .with_ttl(timedelta(seconds=600))
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_attributes(attrs)
    )

    return ParticipantToken(
        token=token.to_jwt(),
        identity="eval-synthetic-caller",
        room_name=room_name,
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


async def _start_room_egress(
    lk_api: Any,
    room_name: str,
    call_id: str,
    config: VoiceEvalConfig,
) -> str | None:
    """Start a Room Composite Egress to record the eval call audio to S3.

    Returns the egress_id on success, or ``None`` if recording is not
    configured or the egress request fails (non-fatal).
    """
    if not config.recording_s3_bucket:
        return None

    try:
        from livekit.api import (
            EncodedFileOutput,
            EncodedFileType,
            RoomCompositeEgressRequest,
            S3Upload,
        )

        s3_key = f"eval-recordings/{room_name}/{call_id}.ogg"

        s3_upload = S3Upload(
            bucket=config.recording_s3_bucket,
            region=config.recording_s3_region,
        )

        request = RoomCompositeEgressRequest(
            room_name=room_name,
            audio_only=True,
            file_outputs=[
                EncodedFileOutput(
                    file_type=EncodedFileType.OGG,
                    filepath=s3_key,
                    s3=s3_upload,
                )
            ],
        )

        egress_info = await lk_api.egress.start_room_composite_egress(request)
        egress_id: str = egress_info.egress_id

        logger.info(
            "Room egress started for voice eval",
            extra={
                "egress_id": egress_id,
                "room_name": room_name,
                "s3_key": s3_key,
            },
        )
        return egress_id

    except Exception:
        logger.exception(
            "Failed to start room egress (recording will be unavailable)",
            extra={"room_name": room_name, "call_id": call_id},
        )
        return None


async def _stop_and_collect_egress(
    lk_api: Any,
    egress_id: str,
    bucket: str,
) -> str | None:
    """Stop the egress and poll until the recording file is available.

    Returns the S3 URI of the recorded file, or ``None`` on failure.
    """
    # LiveKit EgressStatus enum values (from livekit.protocol.egress):
    #   EGRESS_STARTING=0, EGRESS_ACTIVE=1, EGRESS_ENDING=2,
    #   EGRESS_COMPLETE=3, EGRESS_FAILED=4, EGRESS_ABORTED=5,
    #   EGRESS_LIMIT_REACHED=6
    _TERMINAL_SUCCESS = 3  # EGRESS_COMPLETE
    _TERMINAL_FAILURE = {4, 5, 6}  # FAILED, ABORTED, LIMIT_REACHED
    _TERMINAL_STATUSES = {_TERMINAL_SUCCESS} | _TERMINAL_FAILURE

    try:
        from livekit.api import StopEgressRequest

        await lk_api.egress.stop_egress(StopEgressRequest(egress_id=egress_id))
    except Exception:
        # Stop may fail if egress already reached a terminal state.
        # Continue polling — the recording may still be available.
        logger.warning("Failed to stop egress %s (will still poll)", egress_id)

    # Poll until egress reaches a terminal state.
    elapsed = 0.0
    while elapsed < _EGRESS_POLL_TIMEOUT_S:
        try:
            from livekit.api import ListEgressRequest

            response = await lk_api.egress.list_egress(
                ListEgressRequest(egress_id=egress_id)
            )
            if response.items:
                info = response.items[0]
                if info.status in _TERMINAL_FAILURE:
                    logger.warning(
                        "Egress failed — recording unavailable",
                        extra={
                            "egress_id": egress_id,
                            "status": info.status,
                        },
                    )
                    return None
                if info.status == _TERMINAL_SUCCESS:
                    if info.file_results:
                        location: str = info.file_results[0].location
                        if location:
                            # FileInfo.location is a full URI
                            # (e.g. "s3://bucket/path/file.ogg").
                            # Only prefix if it's a bare path.
                            s3_uri = (
                                location
                                if "://" in location
                                else f"s3://{bucket}/{location}"
                            )
                            logger.info(
                                "Egress recording available",
                                extra={
                                    "egress_id": egress_id,
                                    "s3_uri": s3_uri,
                                },
                            )
                            return s3_uri
                    logger.warning(
                        "Egress completed but no file results",
                        extra={
                            "egress_id": egress_id,
                            "status": info.status,
                        },
                    )
                    return None
        except Exception:
            logger.exception("Error polling egress %s", egress_id)

        await asyncio.sleep(_EGRESS_POLL_INTERVAL_S)
        elapsed += _EGRESS_POLL_INTERVAL_S

    logger.warning(
        "Egress poll timed out",
        extra={"egress_id": egress_id, "timeout_s": _EGRESS_POLL_TIMEOUT_S},
    )
    return None


async def run_voice_scenario(
    scenario: EvalScenario,
    config: VoiceEvalConfig,
    session: AsyncSession,
    caller_factory: SyntheticCallerFactory | None = None,
    dialed_number: str = "",
) -> ConversationRecord:
    """Run a single voice eval scenario end-to-end.

    Orchestrates the full Option B flow:
        1. Resolve persona → VoiceProfile
        2. Create LiveKit room
        3. Generate call_id and participant token (with sip.callID attribute)
        4. Run synthetic call (TTS turns → agent responds)
        5. Collect results from DB via VoiceResultCollector
        6. Convert to ConversationRecord for evaluators

    Args:
        scenario: The eval scenario to run.
        config: Voice eval configuration (credentials, timeouts).
        session: Database session for result collection.
        caller_factory: Factory for creating synthetic callers. If None,
            a default ``SyntheticCaller`` is created that connects via
            livekit-rtc and publishes TTS audio into the room.

    Returns:
        ConversationRecord ready for the evaluator pipeline.

    Raises:
        ValueError: If voice eval config is invalid.
        TimeoutError: If the call does not complete within the timeout.
    """
    voice_profile = resolve_persona(scenario.persona)
    # Use 16kHz to match the agent's audio input sample rate (SAMPLE_RATE=16000).
    # The agent's Silero VAD is trained on 16kHz audio, and mismatched rates
    # cause the VAD to miss synthetic caller speech entirely.
    voice_profile.sample_rate = 16000
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
    egress_id: str | None = None
    lk_api: Any = None
    audio_recording_s3_uri: str | None = None
    try:
        # 1. Create room
        room_config = RoomConfig(
            empty_timeout_s=config.room_empty_timeout_s,
            agent_name=config.agent_name,
        )
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

        # 2. Generate call_id and participant token.
        # The call_id is embedded in participant attributes so the LiveKit
        # agent reads it from attrs["sip.callID"] (same key as real SIP calls).
        call_id = f"eval-{uuid.uuid4().hex[:16]}"
        caller_token = _generate_caller_token(
            orchestrator,
            room_name=created_room_name,
            call_id=call_id,
            dialed_number=dialed_number,
        )

        # 2b. Start room egress to record audio (if configured).
        # Uses a separate LiveKitAPI instance so the orchestrator's internal
        # client is not affected.
        if config.recording_s3_bucket:
            from livekit.api import LiveKitAPI

            lk_api = LiveKitAPI(
                url=config.livekit_url,
                api_key=config.livekit_api_key,
                api_secret=config.livekit_api_secret,
            )
            egress_id = await _start_room_egress(
                lk_api, created_room_name, call_id, config
            )

        # 3. Resolve caller factory (use default SyntheticCaller if none)
        if caller_factory is None:
            from services.eval_service._synthetic_caller import SyntheticCaller

            caller_factory = SyntheticCaller(
                livekit_url=config.livekit_url,
            )

        # 4. Run synthetic call (bounded by call_timeout_s)
        call_id = await asyncio.wait_for(
            caller_factory.run_call(
                room_info=room_info,
                caller_token=caller_token.token,
                turns=turn_texts,
                voice_profile=voice_profile,
                tts_engine=tts_engine,
                call_id=call_id,
            ),
            timeout=config.call_timeout_s,
        )

        # 4b. Stop egress and retrieve the recording URI.
        if egress_id is not None and lk_api is not None:
            audio_recording_s3_uri = await _stop_and_collect_egress(
                lk_api, egress_id, config.recording_s3_bucket
            )
            egress_id = None  # Prevent double-stop in finally

        # 5. Collect results
        assert isinstance(created_room_name, str)
        room_name = created_room_name
        collector = VoiceResultCollector(session)
        voice_result: VoiceEvalResult = await collector.collect(
            call_id=call_id,
            room_name=room_name,
            timeout_s=config.call_timeout_s,
            audio_recording_s3_uri=audio_recording_s3_uri,
        )

        logger.info(
            "Voice eval results collected",
            extra={
                "call_id": call_id,
                "room_name": created_room_name,
                "transcript_length": len(voice_result.transcript),
                "duration_s": voice_result.metrics.duration_seconds,
                "audio_recording_s3_uri": voice_result.audio_recording_s3_uri,
            },
        )

        # 6. Convert to ConversationRecord
        return voice_result.to_conversation_record(scenario)

    finally:
        # Best-effort cleanup — each step is isolated so one failure
        # does not prevent the others from running.
        if egress_id is not None and lk_api is not None:
            try:
                egress_uri = await _stop_and_collect_egress(
                    lk_api, egress_id, config.recording_s3_bucket
                )
                if audio_recording_s3_uri is None:
                    audio_recording_s3_uri = egress_uri
            except Exception:
                logger.exception("Failed to stop egress %s", egress_id)
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
        if lk_api is not None:
            try:
                await lk_api.aclose()
            except Exception:
                logger.exception("Failed to close LiveKit API client")
