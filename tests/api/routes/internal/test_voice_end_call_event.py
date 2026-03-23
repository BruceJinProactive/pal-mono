"""Tests for ConversationEvaluationRequested event publishing in end_voice_call."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from api.routes.internal._voice import (
    _build_audio_recording_reference,
    _extract_transcript_text,
    _publish_livekit_evaluation_event,
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

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
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

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
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

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
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

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
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
async def test_publish_event_with_audio_recording():
    """Test that audio_recording is included in event when provided."""
    project = _make_project()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_project.return_value = project

    audio_recording = AudioRecordingReference(
        s3_uri="s3://test-bucket/recordings/call-123.wav",
        duration_seconds=42.5,
    )

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
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

    with (
        patch("db.session.AsyncSessionLocal") as mock_session_cls,
        patch(f"{VOICE_MODULE}.db") as mock_db,
        patch(f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock) as mock_publish,
    ):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_db.ProjectRepositoryAsync.return_value = mock_repo
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
