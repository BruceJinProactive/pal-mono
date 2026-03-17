"""Tests for ConversationEvaluationRequested event publishing in end_voice_call."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.internal._voice import (
    _extract_transcript_text,
    _publish_livekit_evaluation_event,
)
from events.schema import ConversationEvaluationRequested

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
