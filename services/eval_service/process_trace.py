"""Process trace data model and builder.

Constructs ProcessTrace objects from ConversationRecord data for both
HTTP and voice modes. Used by process verification evaluators (tool_timing,
param_collection, output_use).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Content types
# ---------------------------------------------------------------------------


@dataclass
class TextContent:
    text: str


@dataclass
class AudioContent:
    uri: str
    duration_ms: float | None = None
    format: str | None = None
    transcript: str | None = None


Content = TextContent | AudioContent | None


# ---------------------------------------------------------------------------
# Event and action types
# ---------------------------------------------------------------------------


class EventType:
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    ACTION = "action"


class ActionType:
    TOOL_CALL = "tool_call"
    ESCALATION = "escalation"


# ---------------------------------------------------------------------------
# AgentAction
# ---------------------------------------------------------------------------


@dataclass
class AgentAction:
    action_type: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    result_status: str | None = None
    timestamp_ms: float | None = None


# ---------------------------------------------------------------------------
# TraceEvent
# ---------------------------------------------------------------------------


@dataclass
class TraceEvent:
    event_type: str
    turn_index: int
    timestamp_ms: float | None = None
    content: Content = None
    actions: list[AgentAction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ProcessTrace
# ---------------------------------------------------------------------------


@dataclass
class ProcessTrace:
    scenario_id: str
    driver_mode: str
    events: list[TraceEvent] = field(default_factory=list)

    def get_events(self, event_type: str) -> list[TraceEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def get_actions(self) -> list[tuple[int, AgentAction]]:
        """Return all actions as (turn_index, action) pairs."""
        result: list[tuple[int, AgentAction]] = []
        for event in self.events:
            for action in event.actions:
                result.append((event.turn_index, action))
        return result

    def get_chat_history(self) -> list[dict[str, Any]]:
        """Get conversation as role/content pairs with original Content type."""
        history: list[dict[str, Any]] = []
        for event in self.events:
            if event.event_type == EventType.USER_MESSAGE:
                history.append({"role": "user", "content": event.content})
            elif event.event_type == EventType.AGENT_MESSAGE:
                history.append({"role": "agent", "content": event.content})
        return history


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def get_text(content: Content) -> str | None:
    """Extract text from Content: .text for TextContent, .transcript for AudioContent."""
    if isinstance(content, TextContent):
        return content.text
    if isinstance(content, AudioContent):
        return content.transcript
    return None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _extract_tool_name(tc: dict[str, Any]) -> str:
    """Extract tool name from a tool_call dict (supports event-payload and flat)."""
    payload = tc.get("payload", {})
    name = payload.get("tool_name", "")
    if name:
        return str(name)
    return str(tc.get("tool_name") or tc.get("tool", ""))


def _extract_tool_args(tc: dict[str, Any]) -> dict[str, Any]:
    """Extract arguments from a tool_call dict."""
    payload = tc.get("payload", {})
    if payload.get("tool_name"):
        raw = payload.get("arguments")
    else:
        raw = tc.get("args") or tc.get("arguments")
    return dict(raw) if isinstance(raw, dict) else {}


def _extract_tool_result(tc: dict[str, Any]) -> dict[str, Any] | None:
    """Extract tool result from a tool_call dict."""
    payload = tc.get("payload", {})
    result = payload.get("result") or tc.get("result")
    if result is not None:
        return dict(result) if isinstance(result, dict) else {"value": result}
    return None


def _extract_result_status(tc: dict[str, Any]) -> str | None:
    """Extract result status from a tool_call dict."""
    payload = tc.get("payload", {})
    return payload.get("result_status") or tc.get("result_status") or tc.get("status")


def build_process_trace(
    record: Any,
    driver_mode: str | None = None,
) -> "ProcessTrace":
    """Build a ProcessTrace from a ConversationRecord.

    Supports both HTTP and voice modes by detecting record.is_voice.

    Args:
        record: ConversationRecord instance.
        driver_mode: Override driver mode string. If None, inferred from record.

    Returns:
        ProcessTrace with events populated from the record.
    """
    from services.eval_service._evaluators import ConversationRecord

    assert isinstance(record, ConversationRecord)

    mode = driver_mode or ("voice" if record.is_voice else "http")
    trace = ProcessTrace(
        scenario_id=record.scenario.scenario_id,
        driver_mode=mode,
    )

    if record.is_voice and record.voice_transcript:
        _build_from_voice(trace, record)
    else:
        _build_from_http(trace, record)

    _attach_tool_calls(trace, record.tool_calls)

    return trace


def _build_from_http(trace: ProcessTrace, record: Any) -> None:
    """Populate trace events from HTTP ConversationRecord.turns."""
    turn_index = 0
    for turn in record.turns:
        user_text = turn.get("user", "")
        assistant_text = turn.get("assistant", "")

        if user_text:
            trace.events.append(
                TraceEvent(
                    event_type=EventType.USER_MESSAGE,
                    turn_index=turn_index,
                    timestamp_ms=None,
                    content=TextContent(text=user_text),
                )
            )

        if assistant_text:
            trace.events.append(
                TraceEvent(
                    event_type=EventType.AGENT_MESSAGE,
                    turn_index=turn_index,
                    timestamp_ms=None,
                    content=TextContent(text=assistant_text),
                )
            )

        turn_index += 1


def _build_from_voice(trace: ProcessTrace, record: Any) -> None:
    """Populate trace events from voice ConversationRecord.voice_transcript."""
    audio_uri = record.audio_recording_s3_uri or ""

    turn_index = 0
    for entry in record.voice_transcript:
        role = entry.get("role", "")
        content_text = entry.get("content", "")
        start_time = entry.get("start_time")
        end_time = entry.get("end_time")

        timestamp_ms = start_time * 1000 if start_time is not None else None
        duration_ms = None
        if start_time is not None and end_time is not None:
            duration_ms = (end_time - start_time) * 1000

        content = AudioContent(
            uri=audio_uri,
            duration_ms=duration_ms,
            format="ogg",
            transcript=content_text,
        )

        if role == "user":
            event_type = EventType.USER_MESSAGE
        elif role == "assistant":
            event_type = EventType.AGENT_MESSAGE
        else:
            continue

        trace.events.append(
            TraceEvent(
                event_type=event_type,
                turn_index=turn_index,
                timestamp_ms=timestamp_ms,
                content=content,
            )
        )

        if event_type == EventType.AGENT_MESSAGE:
            turn_index += 1


def _resolve_tool_turn(tc: dict[str, Any], agent_turn_indices: list[int]) -> int:
    """Determine which turn a tool call belongs to.

    Uses _msg_index metadata (set by the runner) to find the closest preceding
    agent turn. Falls back to the last agent turn if no metadata is present.
    """
    if not agent_turn_indices:
        return 0

    msg_index = tc.get("_msg_index")
    if isinstance(msg_index, int) and agent_turn_indices:
        # Map message index to the closest agent turn that is <= msg_index
        preceding = [idx for idx in agent_turn_indices if idx <= msg_index]
        if preceding:
            return preceding[-1]
        return agent_turn_indices[0]

    # Fallback: assign to last agent turn
    return agent_turn_indices[-1]


def _attach_tool_calls(trace: ProcessTrace, tool_calls: list[dict[str, Any]]) -> None:
    """Attach tool calls to the trace as ACTION events.

    Tool calls are assigned to the agent turn that triggered them. When
    ``_msg_index`` metadata is present (set by the runner), it maps to the
    closest preceding agent turn. Otherwise falls back to the last agent turn.
    """
    if not tool_calls:
        return

    agent_events = [e for e in trace.events if e.event_type == EventType.AGENT_MESSAGE]
    agent_turn_indices = [e.turn_index for e in agent_events]

    for tc in tool_calls:
        tool_name = _extract_tool_name(tc)
        tool_args = _extract_tool_args(tc)
        tool_result = _extract_tool_result(tc)
        result_status = _extract_result_status(tc)

        turn_index = _resolve_tool_turn(tc, agent_turn_indices)

        action = AgentAction(
            action_type=ActionType.TOOL_CALL,
            arguments={"tool_name": tool_name, **tool_args},
            result=tool_result,
            result_status=result_status,
            timestamp_ms=None,
        )

        trace.events.append(
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=turn_index,
                timestamp_ms=None,
                actions=[action],
            )
        )
