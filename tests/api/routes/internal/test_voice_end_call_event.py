"""Tests for ConversationEvaluationRequested event publishing in end_voice_call."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from api.routes.internal._voice import (
    _build_audio_recording_reference,
    _extract_transcript_text,
    _persist_conversation_messages,
    _publish_livekit_evaluation_event,
)
from api.schemas.internal.voice_init import (
    CallMetricsReport,
    InterruptionEvent,
    TurnLatency,
)
from events.schema import (
    AudioRecordingReference,
    BaseEvent,
    ConversationEvaluationRequested,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(**overrides):
    project = MagicMock()
    project.id = overrides.get("id", uuid.uuid4())
    project.account_id = overrides.get("account_id", uuid.uuid4())
    project.account = MagicMock()
    project.account.name = overrides.get("account_name", "test-account")
    return project


def _make_analytics():
    return {
        "ended_reason": MagicMock(value="customer_ended"),
        "call_purpose": [MagicMock(value="ordering")],
        "user_satisfaction": MagicMock(value="positive"),
        "language": MagicMock(value="english"),
    }


def _common_kwargs(**overrides):
    defaults = {
        "conversation_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "call_id": "test-call-123",
        "duration_seconds": 42.5,
        "close_reason": "customer_ended",
        "conversation_history": [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Hi there"},
        ],
        "analytics": _make_analytics(),
        "channel": "voice",
        "is_test": False,
        "customer_converted": None,
        "audio_recording": None,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# _extract_transcript_text tests
# ---------------------------------------------------------------------------


class TestExtractTranscriptText:
    def test_string_content(self):
        assert _extract_transcript_text({"content": "Hello"}) == "Hello"

    def test_list_content_with_text(self):
        assert _extract_transcript_text({"content": [{"text": "Hi"}]}) == "Hi"

    def test_empty_list_content(self):
        assert _extract_transcript_text({"content": []}) == ""

    def test_list_with_non_dict(self):
        assert _extract_transcript_text({"content": ["plain"]}) == "['plain']"

    def test_none_content(self):
        assert _extract_transcript_text({"content": None}) == ""

    def test_missing_content(self):
        assert _extract_transcript_text({}) == ""


# ---------------------------------------------------------------------------
# _build_audio_recording_reference tests
# ---------------------------------------------------------------------------


class TestBuildAudioRecordingReference:
    def test_valid_s3_uri_with_extension(self):
        result = _build_audio_recording_reference(
            "s3://my-bucket/recordings/call-123.wav", 42.5
        )
        assert result is not None
        assert result.s3_uri == "s3://my-bucket/recordings/call-123.wav"
        assert result.duration_seconds == 42.5

    def test_valid_s3_uri_mp3_format(self):
        result = _build_audio_recording_reference("s3://my-bucket/call.mp3", 30.0)
        assert result is not None
        assert result.duration_seconds == 30.0

    def test_valid_s3_uri_no_extension(self):
        result = _build_audio_recording_reference(
            "s3://my-bucket/recordings/call-123", 42.5
        )
        assert result is not None
        assert result.s3_uri == "s3://my-bucket/recordings/call-123"

    def test_none_uri(self):
        result = _build_audio_recording_reference(None, 42.5)
        assert result is None

    def test_empty_string_uri(self):
        result = _build_audio_recording_reference("", 42.5)
        assert result is None

    def test_invalid_uri_not_s3(self):
        result = _build_audio_recording_reference(
            "https://example.com/recording.wav", 42.5
        )
        assert result is None

    def test_invalid_uri_no_bucket(self):
        result = _build_audio_recording_reference("s3://", 42.5)
        assert result is None

    def test_invalid_uri_no_key(self):
        result = _build_audio_recording_reference("s3://bucket", 42.5)
        assert result is None

    def test_invalid_uri_empty_key(self):
        result = _build_audio_recording_reference("s3://bucket/", 42.5)
        assert result is None


# ---------------------------------------------------------------------------
# _publish_livekit_evaluation_event tests
# ---------------------------------------------------------------------------

VOICE_MODULE = "api.routes.internal._voice"


@pytest.mark.asyncio
async def test_publish_event_success():
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs()
        await _publish_livekit_evaluation_event(**kwargs)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert event.call_id == "test-call-123"
        assert event.account_name == "test-account"
        assert event.call_metadata["duration_seconds"] == 42.5
        assert event.call_metadata["ended_reason"] == "customer_ended"
        assert event.call_metadata["call_purpose"] == ["ordering"]
        assert len(event.transcript) == 2
        assert event.transcript[0]["speaker"] == "agent"
        assert event.transcript[1]["speaker"] == "user"


@pytest.mark.asyncio
async def test_publish_event_no_analytics_uses_close_reason():
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        # LiveKit sends hyphenated strings; the fallback path must normalise them.
        kwargs = _common_kwargs(
            analytics=None, close_reason="silence-timed-out", conversation_history=[]
        )
        await _publish_livekit_evaluation_event(**kwargs)

        event = mock_publish.call_args[0][0]
        assert event.call_metadata["ended_reason"] == "silence_timeout"
        assert event.call_metadata["call_purpose"] == []
        assert event.call_metadata["language"] == "english"


@pytest.mark.asyncio
async def test_publish_event_project_not_found():
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = None

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
        patch(f"{VOICE_MODULE}.logger") as mock_logger,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo

        await _publish_livekit_evaluation_event(**_common_kwargs())

        mock_publish.assert_not_called()
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_publish_event_exception_does_not_propagate():
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
        patch(f"{VOICE_MODULE}.logger") as mock_logger,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_publish.side_effect = RuntimeError("EventBridge unavailable")

        # Should NOT raise
        await _publish_livekit_evaluation_event(**_common_kwargs())

        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_publish_event_returns_false_logs_warning():
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
        patch(f"{VOICE_MODULE}.logger") as mock_logger,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_publish.return_value = False

        await _publish_livekit_evaluation_event(**_common_kwargs())

        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_publish_event_content_list_format():
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(
            conversation_history=[
                {"role": "assistant", "content": [{"text": "Welcome!"}]},
                {"role": "user", "content": [{"text": "Thanks"}]},
                {"role": "system", "content": "ignored"},
            ],
        )
        await _publish_livekit_evaluation_event(**kwargs)

        event = mock_publish.call_args[0][0]
        assert len(event.transcript) == 2
        assert event.transcript[0]["text"] == "Welcome!"
        assert event.transcript[1]["text"] == "Thanks"


@pytest.mark.asyncio
async def test_publish_event_no_analytics_unknown_close_reason_defaults_to_other():
    """Unrecognised LiveKit close_reason values should fall back to 'other'."""
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(
            analytics=None,
            close_reason="some-unknown-livekit-reason",
            conversation_history=[],
        )
        await _publish_livekit_evaluation_event(**kwargs)

        event = mock_publish.call_args[0][0]
        assert event.call_metadata["ended_reason"] == "other"


@pytest.mark.asyncio
async def test_publish_event_with_tool_calls():
    """Test that tool_calls are populated from database records."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    # Mock tool call records
    mock_tool_call_1 = MagicMock()
    mock_tool_call_1.tool_name = "get_menu"
    mock_tool_call_1.is_error = False
    mock_tool_call_1.error_type = None

    mock_tool_call_2 = MagicMock()
    mock_tool_call_2.tool_name = "place_order"
    mock_tool_call_2.is_error = True
    mock_tool_call_2.error_type = "APIError"

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = [
        mock_tool_call_1,
        mock_tool_call_2,
    ]

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        await _publish_livekit_evaluation_event(**kwargs)

        # Verify tool call repo was called with correct conversation_id
        mock_tool_call_repo.get_tool_calls_by_conversation.assert_called_once_with(
            conversation_id
        )

        # Verify event contains mapped tool calls
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert len(event.tool_calls) == 2
        assert event.tool_calls[0] == {
            "function_name": "get_menu",
            "is_error": False,
            "error_type": None,
        }
        assert event.tool_calls[1] == {
            "function_name": "place_order",
            "is_error": True,
            "error_type": "APIError",
        }


@pytest.mark.asyncio
async def test_publish_event_with_no_tool_calls():
    """Test that tool_calls is empty list when no records exist."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    # Mock empty tool call records
    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        await _publish_livekit_evaluation_event(**kwargs)

        # Verify event contains empty tool_calls list
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert event.tool_calls == []


@pytest.mark.asyncio
async def test_publish_event_with_audio_recording():
    """Test that audio_recording is included in event when provided."""
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    audio_recording = AudioRecordingReference(
        s3_uri="s3://test-bucket/recordings/call-123.wav",
        duration_seconds=42.5,
    )

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(audio_recording=audio_recording)
        await _publish_livekit_evaluation_event(**kwargs)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert event.audio_recording is not None
        assert (
            event.audio_recording.s3_uri == "s3://test-bucket/recordings/call-123.wav"
        )
        assert event.audio_recording.duration_seconds == 42.5


@pytest.mark.asyncio
async def test_publish_event_without_audio_recording():
    """Test that event is valid when audio_recording is None."""
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(audio_recording=None)
        await _publish_livekit_evaluation_event(**kwargs)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert event.audio_recording is None


class TestEventSerialization:
    """Tests for ConversationEvaluationRequested.to_detail() with audio recording."""

    def test_to_detail_with_audio_recording(self):
        event = ConversationEvaluationRequested(
            conversation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            call_id="test-call",
            account_id=UUID("12345678-1234-1234-1234-123456789def"),
            account_name="test-account",
            project_id=UUID("12345678-1234-1234-1234-123456789aaa"),
            user_id=UUID("12345678-1234-1234-1234-123456789bbb"),
            is_test=False,
            channel="voice",
            call_metadata={},
            transcript=[],
            tool_calls=[],
            turn_latencies_ms=[],
            audio_recording=AudioRecordingReference(
                s3_uri="s3://bucket/recordings/room/call.ogg",
                duration_seconds=42.5,
            ),
        )
        detail = event.to_detail()
        assert detail["audio_recording"] == {
            "s3_uri": "s3://bucket/recordings/room/call.ogg",
            "duration_seconds": 42.5,
        }
        assert "conversation_id" in detail

    def test_to_detail_without_audio_recording(self):
        event = ConversationEvaluationRequested(
            conversation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            call_id="test-call",
            account_id=UUID("12345678-1234-1234-1234-123456789def"),
            account_name="test-account",
            project_id=UUID("12345678-1234-1234-1234-123456789aaa"),
            user_id=UUID("12345678-1234-1234-1234-123456789bbb"),
            is_test=False,
            channel="voice",
            call_metadata={},
            transcript=[],
            tool_calls=[],
            turn_latencies_ms=[],
        )
        detail = event.to_detail()
        assert "audio_recording" not in detail

    def test_to_detail_audio_recording_without_duration(self):
        event = ConversationEvaluationRequested(
            conversation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            call_id="test-call",
            account_id=UUID("12345678-1234-1234-1234-123456789def"),
            account_name="test-account",
            project_id=UUID("12345678-1234-1234-1234-123456789aaa"),
            user_id=UUID("12345678-1234-1234-1234-123456789bbb"),
            is_test=False,
            channel="voice",
            call_metadata={},
            transcript=[],
            tool_calls=[],
            turn_latencies_ms=[],
            audio_recording=AudioRecordingReference(
                s3_uri="s3://bucket/recordings/room/call.ogg",
            ),
        )
        detail = event.to_detail()
        rec = detail["audio_recording"]
        assert rec["s3_uri"] == "s3://bucket/recordings/room/call.ogg"
        assert "duration_seconds" not in rec

    def test_serialize_dataclass_helper(self):
        ref = AudioRecordingReference(
            s3_uri="s3://bucket/test.wav",
            duration_seconds=10.0,
        )
        result = BaseEvent._serialize_dataclass(ref)
        assert result == {
            "s3_uri": "s3://bucket/test.wav",
            "duration_seconds": 10.0,
        }


# ---------------------------------------------------------------------------
# Metrics wiring into evaluation event
# ---------------------------------------------------------------------------


def _make_metrics(
    turns: list[TurnLatency] | None = None,
    interruptions: list[InterruptionEvent] | None = None,
) -> CallMetricsReport:
    return CallMetricsReport(
        turn_latencies_ms=turns or [],
        interruption_events=interruptions or [],
    )


async def _publish_with_metrics(
    metrics: CallMetricsReport | None = None,
    conversation_history: list[dict] | None = None,
) -> ConversationEvaluationRequested:
    """Helper: call _publish_livekit_evaluation_event and return the fired event."""
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(metrics=metrics)
        if conversation_history is not None:
            kwargs["conversation_history"] = conversation_history
        await _publish_livekit_evaluation_event(**kwargs)

        mock_publish.assert_called_once()
        return mock_publish.call_args[0][0]


class TestMetricsWiringIntoEvent:
    """Tests that CallMetricsReport data flows into ConversationEvaluationRequested."""

    @pytest.mark.asyncio
    async def test_no_metrics_produces_empty_latencies(self) -> None:
        event = await _publish_with_metrics(metrics=None)
        assert event.turn_latencies_ms == []
        assert event.interruption_events == []

    @pytest.mark.asyncio
    async def test_turn_latencies_computed_from_metrics(self) -> None:
        turns = [
            TurnLatency(
                turn_index=0,
                timestamp=1000.0,
                stt_duration_ms=100.0,
                llm_duration_ms=300.0,
                tts_duration_ms=200.0,
            ),
            TurnLatency(
                turn_index=1,
                timestamp=1010.0,
                stt_duration_ms=50.0,
                llm_duration_ms=400.0,
                tts_duration_ms=150.0,
            ),
        ]
        event = await _publish_with_metrics(metrics=_make_metrics(turns=turns))
        assert event.turn_latencies_ms == [600.0, 600.0]

    @pytest.mark.asyncio
    async def test_interruption_events_passed_through(self) -> None:
        interruptions = [
            InterruptionEvent(turn_index=0, timestamp=1001.0, source="tts"),
            InterruptionEvent(turn_index=1, timestamp=1011.0, source="llm"),
        ]
        event = await _publish_with_metrics(
            metrics=_make_metrics(interruptions=interruptions)
        )
        assert len(event.interruption_events) == 2
        assert event.interruption_events[0] == {
            "turn_index": 0,
            "timestamp": 1001.0,
            "source": "tts",
        }
        assert event.interruption_events[1] == {
            "turn_index": 1,
            "timestamp": 1011.0,
            "source": "llm",
        }

    @pytest.mark.asyncio
    async def test_transcript_timestamps_from_metrics(self) -> None:
        """Agent greeting before first user msg gets 0.0; user msg advances turn."""
        turns = [
            TurnLatency(turn_index=0, timestamp=1000.0),
            TurnLatency(turn_index=1, timestamp=1010.0),
        ]
        conversation_history = [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Hi there"},
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "I'd like to order"},
        ]
        event = await _publish_with_metrics(
            metrics=_make_metrics(turns=turns),
            conversation_history=conversation_history,
        )
        # Greeting (before any user msg) → 0.0
        assert event.transcript[0]["start_time"] == 0.0
        assert event.transcript[0]["end_time"] == 0.0
        # First user msg → turn 0
        assert event.transcript[1]["start_time"] == 1000.0
        assert event.transcript[1]["end_time"] == 1010.0
        # Agent reply shares turn 0
        assert event.transcript[2]["start_time"] == 1000.0
        assert event.transcript[2]["end_time"] == 1010.0
        # Second user msg → turn 1
        assert event.transcript[3]["start_time"] == 1010.0
        assert event.transcript[3]["end_time"] == 0.0  # no next turn

    @pytest.mark.asyncio
    async def test_transcript_timestamps_fallback_without_metrics(self) -> None:
        event = await _publish_with_metrics(metrics=None)
        for entry in event.transcript:
            assert entry["start_time"] == 0.0
            assert entry["end_time"] == 0.0

    @pytest.mark.asyncio
    async def test_more_user_messages_than_turns(self) -> None:
        """When there are more user messages than metric turns, extras get 0.0."""
        turns = [TurnLatency(turn_index=0, timestamp=1000.0)]
        conversation_history = [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Hi there"},
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "Never mind"},
        ]
        event = await _publish_with_metrics(
            metrics=_make_metrics(turns=turns),
            conversation_history=conversation_history,
        )
        assert len(event.transcript) == 4
        # Greeting → 0.0 (before first user msg)
        assert event.transcript[0]["start_time"] == 0.0
        # First user msg → turn 0
        assert event.transcript[1]["start_time"] == 1000.0
        # Agent reply shares turn 0
        assert event.transcript[2]["start_time"] == 1000.0
        # Second user msg → turn 1, but no metric turn exists → 0.0
        assert event.transcript[3]["start_time"] == 0.0


# ---------------------------------------------------------------------------
# _persist_conversation_messages tests
# ---------------------------------------------------------------------------


class TestPersistConversationMessages:
    """Tests for the message persistence helper used in end_voice_call."""

    def test_persists_user_and_assistant_messages(self) -> None:
        session = MagicMock()
        conv_id = uuid.uuid4()
        history = [
            {
                "role": "assistant",
                "content": "Hello!",
                "start_time": 1.0,
                "end_time": 2.0,
            },
            {"role": "user", "content": "Hi there", "start_time": 2.5, "end_time": 3.5},
            {"role": "system", "content": "ignored"},
        ]

        _persist_conversation_messages(
            session, conv_id, MagicMock(value="ACTIVE"), history
        )

        assert session.add.call_count == 2
        added_msgs = [call.args[0] for call in session.add.call_args_list]
        assert added_msgs[0].conversation_id == conv_id
        assert added_msgs[0].body["role"] == "assistant"
        assert added_msgs[1].body["role"] == "user"

    def test_skips_when_conversation_already_closed(self) -> None:
        from db.tables.conversations import ConversationStatus

        session = MagicMock()
        history = [{"role": "user", "content": "Hi"}]

        _persist_conversation_messages(
            session, uuid.uuid4(), ConversationStatus.CLOSED, history
        )

        session.add.assert_not_called()

    def test_skips_when_conversation_closing(self) -> None:
        from db.tables.conversations import ConversationStatus

        session = MagicMock()
        history = [{"role": "user", "content": "Hi"}]

        _persist_conversation_messages(
            session, uuid.uuid4(), ConversationStatus.CLOSING, history
        )

        session.add.assert_not_called()

    def test_empty_conversation_history(self) -> None:
        session = MagicMock()

        _persist_conversation_messages(
            session, uuid.uuid4(), MagicMock(value="ACTIVE"), []
        )

        session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Tool calls from messages.body fallback (PAL-9828)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_event_tool_calls_from_messages_body():
    """Test fallback to read tool_calls from messages.body when tool_call_records is empty."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    # Mock empty tool call records (triggers fallback)
    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    # Mock messages with tool_calls in body
    mock_message_1 = MagicMock()
    mock_message_1.body = {
        "author_type": "agent",
        "tool_calls": [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "lookup_menu",
                    "arguments": {"query": "pizza"},
                    "result": '{"items": ["pepperoni"]}',
                },
            },
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "place_order",
                    "arguments": {"item": "pepperoni"},
                    "result": "Error: ValidationError: Invalid item",
                },
            },
        ],
    }

    mock_message_2 = MagicMock()
    mock_message_2.body = {
        "author_type": "agent",
        "tool_calls": [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "check_hours",
                    "arguments": {},
                    "result": '{"open": true}',
                },
            }
        ],
    }

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = [
        mock_message_1,
        mock_message_2,
    ]

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        await _publish_livekit_evaluation_event(**kwargs)

        # Verify message repo was called to fetch all messages
        mock_message_repo.get_all_messages_by_conversation.assert_called_once_with(
            conversation_id
        )

        # Verify event contains tool calls extracted from messages.body
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert len(event.tool_calls) == 3
        assert event.tool_calls[0] == {
            "function_name": "lookup_menu",
            "is_error": False,
            "error_type": None,
        }
        assert event.tool_calls[1] == {
            "function_name": "place_order",
            "is_error": True,
            "error_type": "ValidationError",
        }
        assert event.tool_calls[2] == {
            "function_name": "check_hours",
            "is_error": False,
            "error_type": None,
        }


@pytest.mark.asyncio
async def test_publish_event_tool_calls_prefers_records_over_messages():
    """Test that tool_call_records take precedence over messages.body."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    # Mock tool call records (should be preferred)
    mock_tool_call_1 = MagicMock()
    mock_tool_call_1.tool_name = "get_menu"
    mock_tool_call_1.is_error = False
    mock_tool_call_1.error_type = None

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = [mock_tool_call_1]

    # Mock messages with tool_calls (should be ignored)
    mock_message = MagicMock()
    mock_message.body = {
        "tool_calls": [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "should_not_appear",
                    "arguments": {},
                    "result": "{}",
                },
            }
        ]
    }

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = [mock_message]

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        await _publish_livekit_evaluation_event(**kwargs)

        # Verify message repo was NOT called (records exist)
        mock_message_repo.get_all_messages_by_conversation.assert_not_called()

        # Verify event contains only tool_call_records data
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert len(event.tool_calls) == 1
        assert event.tool_calls[0]["function_name"] == "get_menu"


@pytest.mark.asyncio
async def test_publish_event_tool_calls_malformed_body_graceful():
    """Test that malformed tool_calls in messages.body are handled gracefully."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    # Mock messages with various malformed structures
    mock_message_1 = MagicMock()
    mock_message_1.body = {
        "tool_calls": [
            "invalid_string",  # Not a dict
            {"type": "tool_call"},  # Missing payload
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "valid_tool",
                    "arguments": {},
                    "result": "success",
                },
            },
        ]
    }

    mock_message_2 = MagicMock()
    mock_message_2.body = None  # No body at all

    mock_message_3 = MagicMock()
    mock_message_3.body = {"other_field": "value"}  # No tool_calls key

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = [
        mock_message_1,
        mock_message_2,
        mock_message_3,
    ]

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        # Should not raise
        await _publish_livekit_evaluation_event(**kwargs)

        # Verify only the valid tool call was extracted
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert len(event.tool_calls) == 1
        assert event.tool_calls[0]["function_name"] == "valid_tool"


@pytest.mark.asyncio
async def test_publish_event_tool_calls_no_messages():
    """Test that empty messages list results in empty tool_calls."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = []

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        await _publish_livekit_evaluation_event(**kwargs)

        mock_message_repo.get_all_messages_by_conversation.assert_called_once_with(
            conversation_id
        )
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert event.tool_calls == []


@pytest.mark.asyncio
async def test_publish_event_tool_calls_skip_empty_tool_name():
    """Test that tool calls with empty or missing tool_name are skipped."""
    project = _make_project()
    conversation_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_project_repo = AsyncMock()
    mock_project_repo.get_project.return_value = project

    mock_tool_call_repo = AsyncMock()
    mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

    # Mock messages with various empty/missing tool_name scenarios
    mock_message = MagicMock()
    mock_message.body = {
        "tool_calls": [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "",  # Empty string - should be skipped
                    "arguments": {},
                    "result": "success",
                },
            },
            {
                "type": "tool_call",
                "payload": {
                    # Missing tool_name key - should be skipped
                    "arguments": {},
                    "result": "success",
                },
            },
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "valid_tool",  # Valid - should be included
                    "arguments": {},
                    "result": "success",
                },
            },
        ]
    }

    mock_message_repo = AsyncMock()
    mock_message_repo.get_all_messages_by_conversation.return_value = [mock_message]

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(
            f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
        ) as mock_tool_call_repo_cls,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_project_repo
        mock_db.MessageRepositoryAsync.return_value = mock_message_repo
        mock_tool_call_repo_cls.return_value = mock_tool_call_repo
        mock_publish.return_value = True

        kwargs = _common_kwargs(conversation_id=conversation_id)
        await _publish_livekit_evaluation_event(**kwargs)

        # Verify only the valid tool call (with non-empty tool_name) was extracted
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert len(event.tool_calls) == 1
        assert event.tool_calls[0]["function_name"] == "valid_tool"
