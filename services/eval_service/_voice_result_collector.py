"""Voice eval result collector.

After a simulated voice eval call completes (via direct room injection),
polls the database for call results and packages them into a format
consumable by the evaluator pipeline.

Flow (Option B — direct room injection):
    1. Room orchestrator creates room, agent + synthetic caller connect
    2. Call runs → agent shutdown callback → POST /internal/voice/end-call
    3. end-call stores conversation + PhoneCall + publishes event
    4. **This collector** polls by call_id until conversation CLOSED,
       then extracts transcript, metrics, and audio reference.

Usage::

    from services.eval_service._voice_result_collector import (
        VoiceResultCollector,
    )

    collector = VoiceResultCollector(session)
    result = await collector.collect(call_id="lk_xxx", room_name="eval-voice-abc")

    # Feed into evaluator pipeline
    record = result.to_conversation_record(scenario)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.conversation_repository import ConversationRepositoryAsync
from db.repositories.message_repository import MessageRepositoryAsync
from db.repositories.phone_call_repository import PhoneCallRepositoryAsync
from db.tables.conversations import ConversationStatus
from services.eval_service._evaluators import ConversationRecord
from services.eval_service.schema import EvalScenario
from utils.log import logger

_DEFAULT_POLL_INTERVAL_S = 3.0
_DEFAULT_TIMEOUT_S = 120.0
_MAX_TRANSCRIPT_MESSAGES = 200


@dataclass
class VoiceCallMetrics:
    """Latency and duration metrics from a completed voice call."""

    duration_seconds: float
    turn_latency_avg: float | None = None
    model_latency_avg: float | None = None
    voice_latency_avg: float | None = None
    transcriber_latency_avg: float | None = None
    endpointing_latency_avg: float | None = None


@dataclass
class VoiceEvalResult:
    """Structured output from a completed voice eval call.

    Contains everything needed to evaluate the call: transcript,
    tool calls, latency metrics, and an optional audio recording URI.
    """

    call_id: str
    room_name: str
    transcript: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metrics: VoiceCallMetrics = field(
        default_factory=lambda: VoiceCallMetrics(duration_seconds=0.0)
    )
    audio_recording_s3_uri: str | None = None
    close_reason: str = ""

    def to_conversation_record(self, scenario: EvalScenario) -> ConversationRecord:
        """Convert to the evaluator-consumable ConversationRecord format.

        Maps the voice transcript into the ``turns`` / ``agent_responses``
        structure that ``evaluate_scenario()`` expects.
        """
        turns: list[dict[str, str]] = []
        agent_responses: list[str] = []

        current_user: str | None = None
        for msg in self.transcript:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                current_user = content
            elif role == "assistant":
                agent_responses.append(content)
                if current_user is not None:
                    turns.append({"user": current_user, "assistant": content})
                    current_user = None

        return ConversationRecord(
            scenario=scenario,
            turns=turns,
            tool_calls=self.tool_calls,
            agent_responses=agent_responses,
        )


def _extract_message_text(body: dict[str, Any]) -> str:
    """Extract text from a message body JSONB field.

    Handles both ``{"content": "text"}`` and
    ``{"content": [{"text": "..."}]}`` formats.
    """
    content = body.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return content[0].get("text", "")
    return str(content or "")


class VoiceResultCollector:
    """Polls the database for voice eval call results.

    After a simulated call ends, the LiveKit agent's shutdown callback
    posts to ``/internal/voice/end-call``, which creates the Conversation
    and PhoneCall records.  This collector waits for that data, then
    packages it for the evaluator pipeline.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def collect(
        self,
        call_id: str,
        room_name: str,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
    ) -> VoiceEvalResult:
        """Wait for call results and return a structured VoiceEvalResult.

        Polls ``conversations`` by *call_id* until status is CLOSED (or
        CLOSING), then reads messages and the PhoneCall record.

        Args:
            call_id: The voice call ID assigned to the eval call.
            room_name: The LiveKit room name (included in the result).
            timeout_s: Maximum seconds to wait before raising TimeoutError.
            poll_interval_s: Seconds between poll attempts.

        Returns:
            VoiceEvalResult with transcript, metrics, and audio URI.

        Raises:
            TimeoutError: If the conversation does not close within *timeout_s*.
        """
        conversation = await self._wait_for_closed_conversation(
            call_id, timeout_s, poll_interval_s
        )

        conversation_id = conversation.id
        ended_reason = conversation.ended_reason or ""

        transcript = await self._extract_transcript(conversation_id)
        metrics, audio_uri = await self._extract_phone_call_data(call_id)

        return VoiceEvalResult(
            call_id=call_id,
            room_name=room_name,
            transcript=transcript,
            tool_calls=[],
            metrics=metrics,
            audio_recording_s3_uri=audio_uri,
            close_reason=ended_reason,
        )

    async def _wait_for_closed_conversation(
        self,
        call_id: str,
        timeout_s: float,
        poll_interval_s: float,
    ) -> Any:
        """Poll until the conversation for *call_id* reaches a terminal state."""
        conv_repo = ConversationRepositoryAsync(self._session)
        terminal_statuses = {ConversationStatus.CLOSED, ConversationStatus.CLOSING}
        elapsed = 0.0

        while elapsed < timeout_s:
            conversation = await conv_repo.get_conversation_by_call_id(call_id)
            if conversation is not None and conversation.status in terminal_statuses:
                logger.info(
                    "Voice eval conversation closed",
                    extra={"call_id": call_id, "status": conversation.status.value},
                )
                return conversation

            logger.debug(
                "Waiting for conversation to close",
                extra={
                    "call_id": call_id,
                    "elapsed_s": elapsed,
                    "status": (
                        conversation.status.value if conversation else "not_found"
                    ),
                },
            )
            await asyncio.sleep(poll_interval_s)
            elapsed += poll_interval_s

        raise TimeoutError(
            f"Voice eval conversation for call_id={call_id!r} "
            f"did not close within {timeout_s}s"
        )

    async def _extract_transcript(self, conversation_id: Any) -> list[dict[str, str]]:
        """Read messages for the conversation and build a transcript."""
        msg_repo = MessageRepositoryAsync(self._session)
        messages = await msg_repo.get_messages_by_conversation(
            conversation_id, limit=_MAX_TRANSCRIPT_MESSAGES
        )

        transcript: list[dict[str, str]] = []
        for msg in messages:
            body = msg.body if isinstance(msg.body, dict) else {}
            role = body.get("role", "")
            if role not in ("user", "assistant"):
                continue
            transcript.append(
                {
                    "role": role,
                    "content": _extract_message_text(body),
                }
            )

        return transcript

    async def _extract_phone_call_data(
        self, call_id: str
    ) -> tuple[VoiceCallMetrics, str | None]:
        """Read the PhoneCall record for latency metrics and audio URI.

        Returns a tuple of (metrics, audio_s3_uri).  If no PhoneCall
        record exists yet, returns default metrics and None.
        """
        pc_repo = PhoneCallRepositoryAsync(self._session)
        phone_call = await pc_repo.get_by_call_id(call_id)

        if phone_call is None:
            logger.warning(
                "No PhoneCall record found for voice eval",
                extra={"call_id": call_id},
            )
            return VoiceCallMetrics(duration_seconds=0.0), None

        metrics = VoiceCallMetrics(
            duration_seconds=phone_call.duration or 0.0,
            turn_latency_avg=phone_call.turn_latency_avg,
            model_latency_avg=phone_call.model_latency_avg,
            voice_latency_avg=phone_call.voice_latency_avg,
            transcriber_latency_avg=phone_call.transcriber_latency_avg,
            endpointing_latency_avg=phone_call.endpointing_latency_avg,
        )

        # audio_recording_s3_uri is not on PhoneCall — it flows through the
        # event payload.  For now we return None; the eval runner can pass
        # the URI from the end-call request if needed.
        return metrics, None
