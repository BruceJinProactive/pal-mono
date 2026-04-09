"""Tests for VoiceResultCollector, VoiceEvalResult, and VoiceCallMetrics."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._voice_result_collector import (
    VoiceCallMetrics,
    VoiceEvalResult,
    VoiceResultCollector,
    _extract_message_text,
)
from services.eval_service.schema import EvalScenario

# ---------------------------------------------------------------------------
# VoiceCallMetrics
# ---------------------------------------------------------------------------


class TestVoiceCallMetrics:
    def test_defaults(self) -> None:
        m = VoiceCallMetrics(duration_seconds=42.5)
        assert m.duration_seconds == 42.5
        assert m.turn_latency_avg is None
        assert m.model_latency_avg is None
        assert m.voice_latency_avg is None
        assert m.transcriber_latency_avg is None
        assert m.endpointing_latency_avg is None

    def test_all_fields(self) -> None:
        m = VoiceCallMetrics(
            duration_seconds=60.0,
            turn_latency_avg=0.5,
            model_latency_avg=120.0,
            voice_latency_avg=80.0,
            transcriber_latency_avg=50.0,
            endpointing_latency_avg=30.0,
        )
        assert m.duration_seconds == 60.0
        assert m.turn_latency_avg == 0.5
        assert m.endpointing_latency_avg == 30.0


# ---------------------------------------------------------------------------
# VoiceEvalResult
# ---------------------------------------------------------------------------


class TestVoiceEvalResult:
    def test_defaults(self) -> None:
        r = VoiceEvalResult(call_id="call-1", room_name="eval-voice-abc")
        assert r.call_id == "call-1"
        assert r.room_name == "eval-voice-abc"
        assert r.transcript == []
        assert r.tool_calls == []
        assert r.audio_recording_s3_uri is None
        assert r.close_reason == ""
        assert r.metrics.duration_seconds == 0.0

    def test_to_conversation_record_basic(self) -> None:
        r = VoiceEvalResult(
            call_id="call-1",
            room_name="room-1",
            transcript=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "What are your hours?"},
                {"role": "assistant", "content": "We are open 9-5."},
            ],
        )
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="greeting",
            test_category="general",
            user_turns=["Hello", "What are your hours?"],
        )

        record = r.to_conversation_record(scenario)

        assert len(record.turns) == 2
        assert record.turns[0] == {"user": "Hello", "assistant": "Hi there!"}
        assert record.turns[1] == {
            "user": "What are your hours?",
            "assistant": "We are open 9-5.",
        }
        assert record.agent_responses == ["Hi there!", "We are open 9-5."]
        assert record.scenario is scenario

    def test_to_conversation_record_empty_transcript(self) -> None:
        r = VoiceEvalResult(call_id="c", room_name="r", transcript=[])
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=["hi"],
        )

        record = r.to_conversation_record(scenario)
        assert record.turns == []
        assert record.agent_responses == []

    def test_to_conversation_record_consecutive_assistant(self) -> None:
        """Assistant messages without a preceding user turn are still captured."""
        r = VoiceEvalResult(
            call_id="c",
            room_name="r",
            transcript=[
                {"role": "assistant", "content": "Welcome!"},
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "How can I help?"},
            ],
        )
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=["Hi"],
        )

        record = r.to_conversation_record(scenario)
        # "Welcome!" has no preceding user turn, so no turn pair for it
        assert len(record.turns) == 1
        assert record.turns[0] == {"user": "Hi", "assistant": "How can I help?"}
        # But both assistant messages are in agent_responses
        assert record.agent_responses == ["Welcome!", "How can I help?"]

    def test_to_conversation_record_preserves_tool_calls(self) -> None:
        r = VoiceEvalResult(
            call_id="c",
            room_name="r",
            tool_calls=[{"tool_name": "get_hours", "args": {}}],
        )
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=["hi"],
        )

        record = r.to_conversation_record(scenario)
        assert record.tool_calls == [{"tool_name": "get_hours", "args": {}}]


# ---------------------------------------------------------------------------
# _extract_message_text
# ---------------------------------------------------------------------------


class TestExtractMessageText:
    def test_string_content(self) -> None:
        assert _extract_message_text({"content": "hello"}) == "hello"

    def test_list_content(self) -> None:
        body = {"content": [{"text": "hello from list"}]}
        assert _extract_message_text(body) == "hello from list"

    def test_empty_list(self) -> None:
        # [] is falsy, so `content or ""` yields "" → str("") == ""
        assert _extract_message_text({"content": []}) == ""

    def test_none_content(self) -> None:
        assert _extract_message_text({"content": None}) == ""

    def test_missing_content(self) -> None:
        assert _extract_message_text({}) == ""

    def test_list_missing_text_key(self) -> None:
        body = {"content": [{"type": "image"}]}
        assert _extract_message_text(body) == ""


# ---------------------------------------------------------------------------
# VoiceResultCollector
# ---------------------------------------------------------------------------


def _make_conversation(
    status: str = "closed",
    call_id: str = "call-123",
    ended_reason: str = "customer_ended",
) -> MagicMock:
    """Create a mock Conversation ORM object."""
    from db.tables.conversations import ConversationStatus

    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.call_id = call_id
    conv.status = ConversationStatus(status)
    conv.ended_reason = ended_reason
    return conv


def _make_message(role: str, content: str) -> MagicMock:
    """Create a mock Message ORM object."""
    msg = MagicMock()
    msg.body = {"role": role, "content": content}
    return msg


def _make_phone_call(
    duration: float = 45.0,
    turn_latency_avg: float | None = 0.3,
) -> MagicMock:
    """Create a mock PhoneCall ORM object."""
    pc = MagicMock()
    pc.duration = duration
    pc.turn_latency_avg = turn_latency_avg
    pc.model_latency_avg = 110.0
    pc.voice_latency_avg = 75.0
    pc.transcriber_latency_avg = 40.0
    pc.endpointing_latency_avg = 25.0
    return pc


class TestVoiceResultCollectorCollect:
    async def test_collect_success(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        conv = _make_conversation()
        messages = [
            _make_message("user", "Hello"),
            _make_message("assistant", "Hi there"),
        ]
        phone_call = _make_phone_call(duration=30.0)

        with (
            patch(
                "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.MessageRepositoryAsync"
            ) as mock_msg_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.PhoneCallRepositoryAsync"
            ) as mock_pc_repo_cls,
        ):
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                return_value=conv
            )
            mock_msg_repo_cls.return_value.get_messages_by_conversation = AsyncMock(
                return_value=messages
            )
            mock_pc_repo_cls.return_value.get_by_call_id = AsyncMock(
                return_value=phone_call
            )

            result = await collector.collect(
                call_id="call-123", room_name="eval-voice-abc"
            )

        assert result.call_id == "call-123"
        assert result.room_name == "eval-voice-abc"
        assert len(result.transcript) == 2
        assert result.transcript[0] == {"role": "user", "content": "Hello"}
        assert result.metrics.duration_seconds == 30.0
        assert result.metrics.turn_latency_avg == 0.3
        assert result.close_reason == "customer_ended"

    async def test_collect_no_phone_call(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        conv = _make_conversation()

        with (
            patch(
                "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.MessageRepositoryAsync"
            ) as mock_msg_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.PhoneCallRepositoryAsync"
            ) as mock_pc_repo_cls,
        ):
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                return_value=conv
            )
            mock_msg_repo_cls.return_value.get_messages_by_conversation = AsyncMock(
                return_value=[]
            )
            mock_pc_repo_cls.return_value.get_by_call_id = AsyncMock(return_value=None)

            result = await collector.collect(call_id="call-123", room_name="room-1")

        assert result.metrics.duration_seconds == 0.0
        assert result.audio_recording_s3_uri is None

    async def test_collect_filters_system_messages(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        conv = _make_conversation()
        messages = [
            _make_message("system", "You are a helpful assistant"),
            _make_message("user", "Hi"),
            _make_message("assistant", "Hello!"),
        ]

        with (
            patch(
                "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.MessageRepositoryAsync"
            ) as mock_msg_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.PhoneCallRepositoryAsync"
            ) as mock_pc_repo_cls,
        ):
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                return_value=conv
            )
            mock_msg_repo_cls.return_value.get_messages_by_conversation = AsyncMock(
                return_value=messages
            )
            mock_pc_repo_cls.return_value.get_by_call_id = AsyncMock(return_value=None)

            result = await collector.collect(call_id="call-123", room_name="room-1")

        # System message should be filtered out
        assert len(result.transcript) == 2
        assert result.transcript[0]["role"] == "user"


class TestVoiceResultCollectorTimeout:
    async def test_timeout_raises(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        # Conversation stays ACTIVE forever
        active_conv = _make_conversation(status="active")

        with patch(
            "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
        ) as mock_conv_repo_cls:
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                return_value=active_conv
            )

            with pytest.raises(TimeoutError, match="did not close"):
                await collector.collect(
                    call_id="call-stuck",
                    room_name="room-1",
                    timeout_s=0.1,
                    poll_interval_s=0.05,
                )

    async def test_timeout_conversation_not_found(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        with patch(
            "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
        ) as mock_conv_repo_cls:
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                return_value=None
            )

            with pytest.raises(TimeoutError, match="did not close"):
                await collector.collect(
                    call_id="call-missing",
                    room_name="room-1",
                    timeout_s=0.1,
                    poll_interval_s=0.05,
                )


class TestVoiceResultCollectorPolling:
    async def test_polls_until_closed(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        active_conv = _make_conversation(status="active")
        closed_conv = _make_conversation(status="closed")

        call_count = 0

        async def get_conv_side_effect(call_id: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return active_conv
            return closed_conv

        with (
            patch(
                "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.MessageRepositoryAsync"
            ) as mock_msg_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.PhoneCallRepositoryAsync"
            ) as mock_pc_repo_cls,
        ):
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                side_effect=get_conv_side_effect
            )
            mock_msg_repo_cls.return_value.get_messages_by_conversation = AsyncMock(
                return_value=[]
            )
            mock_pc_repo_cls.return_value.get_by_call_id = AsyncMock(return_value=None)

            result = await collector.collect(
                call_id="call-123",
                room_name="room-1",
                timeout_s=5.0,
                poll_interval_s=0.01,
            )

        assert call_count == 3
        assert result.call_id == "call-123"

    async def test_accepts_closing_status(self) -> None:
        session = AsyncMock()
        collector = VoiceResultCollector(session)

        closing_conv = _make_conversation(status="closing")

        with (
            patch(
                "services.eval_service._voice_result_collector.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.MessageRepositoryAsync"
            ) as mock_msg_repo_cls,
            patch(
                "services.eval_service._voice_result_collector.PhoneCallRepositoryAsync"
            ) as mock_pc_repo_cls,
        ):
            mock_conv_repo_cls.return_value.get_conversation_by_call_id = AsyncMock(
                return_value=closing_conv
            )
            mock_msg_repo_cls.return_value.get_messages_by_conversation = AsyncMock(
                return_value=[]
            )
            mock_pc_repo_cls.return_value.get_by_call_id = AsyncMock(return_value=None)

            result = await collector.collect(call_id="call-123", room_name="room-1")

        assert result.call_id == "call-123"
