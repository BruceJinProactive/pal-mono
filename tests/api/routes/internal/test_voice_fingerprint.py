"""Tests for fingerprint wiring in voice init + evaluation event (P1-B1d)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.internal._voice import (
    _publish_livekit_evaluation_event,
    init_voice_call,
)
from api.schemas.internal.voice_init import VoiceInitRequest
from db.tables.types import SpeechRate
from events.schema import ConversationEvaluationRequested

VOICE_MODULE = "api.routes.internal._voice"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides) -> VoiceInitRequest:
    defaults = {
        "caller_number": "+15551234567",
        "dialed_number": "+15559876543",
        "call_id": "call-fp-test",
    }
    defaults.update(overrides)
    return VoiceInitRequest(**defaults)


def _make_project(**overrides) -> MagicMock:
    project = MagicMock()
    project.id = overrides.get("id", uuid.uuid4())
    project.timezone = overrides.get("timezone", "America/New_York")
    project.agent_id = overrides.get("agent_id", uuid.uuid4())
    project.account = MagicMock()
    project.account.id = uuid.uuid4()
    return project


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _make_voice_config(**overrides) -> MagicMock:
    vc = MagicMock()
    vc.language = overrides.get("language", "english")
    vc.voice_id = overrides.get("voice_id", "voice-abc")
    vc.speech_rate = overrides.get("speech_rate", SpeechRate.normal)
    vc.first_message = overrides.get("first_message", "Hello!")
    vc.background_sound = overrides.get("background_sound", None)
    vc.pronunciation_dict_id = overrides.get("pronunciation_dict_id", None)
    return vc


def _make_db_agent() -> MagicMock:
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.account = MagicMock()
    agent.account.id = uuid.uuid4()
    return agent


def _make_analytics() -> dict:
    return {
        "ended_reason": MagicMock(value="customer_ended"),
        "call_purpose": [MagicMock(value="ordering")],
        "user_satisfaction": MagicMock(value="positive"),
        "language": MagicMock(value="english"),
    }


def _common_publish_kwargs(**overrides) -> dict:
    defaults = {
        "conversation_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "call_id": "call-fp-test",
        "duration_seconds": 30.0,
        "close_reason": "customer_ended",
        "conversation_history": [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Hi"},
        ],
        "analytics": _make_analytics(),
        "channel": "voice",
        "is_test": False,
        "customer_converted": None,
        "audio_recording": None,
        "agent_fingerprint": None,
        "prompt_fingerprint": None,
    }
    defaults.update(overrides)
    return defaults


def _make_project_mock_for_publish() -> MagicMock:
    project = MagicMock()
    project.id = uuid.uuid4()
    project.account_id = uuid.uuid4()
    project.account = MagicMock()
    project.account.name = "test-account"
    return project


# ---------------------------------------------------------------------------
# Tests: fingerprint stored on conversation during init
# ---------------------------------------------------------------------------


class TestInitVoiceCallFingerprintStored:
    """Fingerprints are computed and persisted on the Conversation row during init."""

    @pytest.mark.asyncio
    async def test_fingerprints_stored_on_conversation(self) -> None:
        """When agent and build_with_fingerprint succeed, fingerprints are written."""
        project = _make_project()
        user = _make_user()
        vc = _make_voice_config()
        db_agent = _make_db_agent()

        mock_conversation = MagicMock()
        mock_conversation.agent_fingerprint = None
        mock_conversation.prompt_fingerprint = None

        session = AsyncMock()

        with (
            patch(
                f"{VOICE_MODULE}.project_service.get_project_async",
                new_callable=AsyncMock,
                return_value=project,
            ),
            patch(
                f"{VOICE_MODULE}.user_service.get_user_async",
                new_callable=AsyncMock,
                return_value=(user, None),
            ),
            patch(
                f"{VOICE_MODULE}.user_service.create_user_async",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(f"{VOICE_MODULE}.db.MessageRepositoryAsync") as mock_msg_cls,
            patch(f"{VOICE_MODULE}.VoiceConfigRepositoryAsync") as mock_vc_cls,
            patch(f"{VOICE_MODULE}.AgentRepositoryAsync") as mock_agent_repo_cls,
            patch(f"{VOICE_MODULE}.RawConfig") as mock_raw_config_cls,
            patch(
                f"{VOICE_MODULE}.db.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
        ):
            mock_msg_cls.return_value = AsyncMock()

            vc_repo = AsyncMock()
            vc_repo.get_voice_configs_by_project.return_value = [vc]
            mock_vc_cls.return_value = vc_repo

            agent_repo = AsyncMock()
            agent_repo.get_agent = AsyncMock(return_value=db_agent)
            mock_agent_repo_cls.return_value = agent_repo

            mock_raw_config_instance = MagicMock()
            mock_raw_config_instance.build_with_fingerprint = AsyncMock(
                return_value=(MagicMock(), "aabbccddeeff0011", "11223344aabbccdd", {})
            )
            mock_raw_config_cls.return_value = mock_raw_config_instance

            conv_repo = AsyncMock()
            conv_repo.get_conversation_by_call_id = AsyncMock(
                return_value=mock_conversation
            )
            mock_conv_repo_cls.return_value = conv_repo

            result = await init_voice_call(_make_request(), session)

        # Fingerprints must be set on the conversation object
        assert mock_conversation.agent_fingerprint == "aabbccddeeff0011"
        assert mock_conversation.prompt_fingerprint == "11223344aabbccdd"
        # session.commit must have been called after stamping
        session.commit.assert_awaited()
        # Response should still be returned correctly
        from api.schemas.internal.voice_init import VoiceInitResponse

        assert isinstance(result, VoiceInitResponse)

    @pytest.mark.asyncio
    async def test_fingerprint_skipped_when_conversation_not_found(self) -> None:
        """If conversation lookup returns None, init still succeeds (warning logged)."""
        project = _make_project()
        user = _make_user()
        vc = _make_voice_config()
        db_agent = _make_db_agent()

        session = AsyncMock()

        with (
            patch(
                f"{VOICE_MODULE}.project_service.get_project_async",
                new_callable=AsyncMock,
                return_value=project,
            ),
            patch(
                f"{VOICE_MODULE}.user_service.get_user_async",
                new_callable=AsyncMock,
                return_value=(user, None),
            ),
            patch(
                f"{VOICE_MODULE}.user_service.create_user_async",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(f"{VOICE_MODULE}.db.MessageRepositoryAsync") as mock_msg_cls,
            patch(f"{VOICE_MODULE}.VoiceConfigRepositoryAsync") as mock_vc_cls,
            patch(f"{VOICE_MODULE}.AgentRepositoryAsync") as mock_agent_repo_cls,
            patch(f"{VOICE_MODULE}.RawConfig") as mock_raw_config_cls,
            patch(
                f"{VOICE_MODULE}.db.ConversationRepositoryAsync"
            ) as mock_conv_repo_cls,
            patch(f"{VOICE_MODULE}.logger") as mock_logger,
        ):
            mock_msg_cls.return_value = AsyncMock()

            vc_repo = AsyncMock()
            vc_repo.get_voice_configs_by_project.return_value = [vc]
            mock_vc_cls.return_value = vc_repo

            agent_repo = AsyncMock()
            agent_repo.get_agent = AsyncMock(return_value=db_agent)
            mock_agent_repo_cls.return_value = agent_repo

            mock_raw_config_instance = MagicMock()
            mock_raw_config_instance.build_with_fingerprint = AsyncMock(
                return_value=(MagicMock(), "aabbccdd", "11223344", {})
            )
            mock_raw_config_cls.return_value = mock_raw_config_instance

            conv_repo = AsyncMock()
            conv_repo.get_conversation_by_call_id = AsyncMock(return_value=None)
            mock_conv_repo_cls.return_value = conv_repo

            from api.schemas.internal.voice_init import VoiceInitResponse

            result = await init_voice_call(_make_request(), session)

        assert isinstance(result, VoiceInitResponse)
        mock_logger.warning.assert_called()
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any(
            "Conversation not found for fingerprinting" in c for c in warning_calls
        )


# ---------------------------------------------------------------------------
# Tests: init succeeds even when fingerprinting fails
# ---------------------------------------------------------------------------


class TestInitVoiceCallFingerprintFailureTolerance:
    """Fingerprint failures must not prevent voice init from returning."""

    @pytest.mark.asyncio
    async def test_init_succeeds_when_build_with_fingerprint_raises(self) -> None:
        """build_with_fingerprint raises -> exception swallowed, VoiceInitResponse returned."""
        project = _make_project()
        user = _make_user()
        vc = _make_voice_config()
        db_agent = _make_db_agent()

        session = AsyncMock()

        with (
            patch(
                f"{VOICE_MODULE}.project_service.get_project_async",
                new_callable=AsyncMock,
                return_value=project,
            ),
            patch(
                f"{VOICE_MODULE}.user_service.get_user_async",
                new_callable=AsyncMock,
                return_value=(user, None),
            ),
            patch(
                f"{VOICE_MODULE}.user_service.create_user_async",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(f"{VOICE_MODULE}.db.MessageRepositoryAsync") as mock_msg_cls,
            patch(f"{VOICE_MODULE}.VoiceConfigRepositoryAsync") as mock_vc_cls,
            patch(f"{VOICE_MODULE}.AgentRepositoryAsync") as mock_agent_repo_cls,
            patch(f"{VOICE_MODULE}.RawConfig") as mock_raw_config_cls,
        ):
            mock_msg_cls.return_value = AsyncMock()

            vc_repo = AsyncMock()
            vc_repo.get_voice_configs_by_project.return_value = [vc]
            mock_vc_cls.return_value = vc_repo

            agent_repo = AsyncMock()
            agent_repo.get_agent = AsyncMock(return_value=db_agent)
            mock_agent_repo_cls.return_value = agent_repo

            mock_raw_config_instance = MagicMock()
            mock_raw_config_instance.build_with_fingerprint = AsyncMock(
                side_effect=RuntimeError("prompt factory failure")
            )
            mock_raw_config_cls.return_value = mock_raw_config_instance

            from api.schemas.internal.voice_init import VoiceInitResponse

            result = await init_voice_call(_make_request(), session)

        # Must still succeed
        assert isinstance(result, VoiceInitResponse)

    @pytest.mark.asyncio
    async def test_init_succeeds_when_agent_not_found(self) -> None:
        """Agent lookup returns None -> fingerprint skipped, init succeeds."""
        project = _make_project()
        user = _make_user()
        vc = _make_voice_config()

        session = AsyncMock()

        with (
            patch(
                f"{VOICE_MODULE}.project_service.get_project_async",
                new_callable=AsyncMock,
                return_value=project,
            ),
            patch(
                f"{VOICE_MODULE}.user_service.get_user_async",
                new_callable=AsyncMock,
                return_value=(user, None),
            ),
            patch(
                f"{VOICE_MODULE}.user_service.create_user_async",
                new_callable=AsyncMock,
                return_value=user,
            ),
            patch(f"{VOICE_MODULE}.db.MessageRepositoryAsync") as mock_msg_cls,
            patch(f"{VOICE_MODULE}.VoiceConfigRepositoryAsync") as mock_vc_cls,
            patch(f"{VOICE_MODULE}.AgentRepositoryAsync") as mock_agent_repo_cls,
        ):
            mock_msg_cls.return_value = AsyncMock()

            vc_repo = AsyncMock()
            vc_repo.get_voice_configs_by_project.return_value = [vc]
            mock_vc_cls.return_value = vc_repo

            agent_repo = AsyncMock()
            agent_repo.get_agent = AsyncMock(return_value=None)
            mock_agent_repo_cls.return_value = agent_repo

            from api.schemas.internal.voice_init import VoiceInitResponse

            result = await init_voice_call(_make_request(), session)

        assert isinstance(result, VoiceInitResponse)


# ---------------------------------------------------------------------------
# Tests: fingerprints passed through to published event
# ---------------------------------------------------------------------------


class TestPublishEventWithFingerprints:
    """Fingerprints are included in the ConversationEvaluationRequested event."""

    @pytest.mark.asyncio
    async def test_fingerprints_present_in_published_event(self) -> None:
        """When fingerprints are set, event carries them."""
        project = _make_project_mock_for_publish()
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_project.return_value = project

        mock_tool_call_repo = AsyncMock()
        mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

        with (
            patch("db.session.AsyncSessionLocal") as mock_session_cls,
            patch(f"{VOICE_MODULE}.db") as mock_db,
            patch(
                f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
            ) as mock_tool_call_repo_cls,
            patch(
                f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock
            ) as mock_publish,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_db.ProjectRepositoryAsync.return_value = mock_repo
            mock_tool_call_repo_cls.return_value = mock_tool_call_repo
            mock_publish.return_value = True

            kwargs = _common_publish_kwargs(
                agent_fingerprint="aabbccddeeff0011",
                prompt_fingerprint="11223344aabbccdd",
            )
            await _publish_livekit_evaluation_event(**kwargs)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert event.agent_fingerprint == "aabbccddeeff0011"
        assert event.prompt_fingerprint == "11223344aabbccdd"

    @pytest.mark.asyncio
    async def test_fingerprints_none_do_not_crash_event(self) -> None:
        """None fingerprints are accepted and omitted from serialized output."""
        project = _make_project_mock_for_publish()
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_project.return_value = project

        mock_tool_call_repo = AsyncMock()
        mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

        with (
            patch("db.session.AsyncSessionLocal") as mock_session_cls,
            patch(f"{VOICE_MODULE}.db") as mock_db,
            patch(
                f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
            ) as mock_tool_call_repo_cls,
            patch(
                f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock
            ) as mock_publish,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_db.ProjectRepositoryAsync.return_value = mock_repo
            mock_tool_call_repo_cls.return_value = mock_tool_call_repo
            mock_publish.return_value = True

            kwargs = _common_publish_kwargs(
                agent_fingerprint=None,
                prompt_fingerprint=None,
            )
            await _publish_livekit_evaluation_event(**kwargs)

        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][0]
        assert isinstance(event, ConversationEvaluationRequested)
        assert event.agent_fingerprint is None
        assert event.prompt_fingerprint is None
        # None values must be absent from serialized detail
        detail = event.to_detail()
        assert "agent_fingerprint" not in detail
        assert "prompt_fingerprint" not in detail

    @pytest.mark.asyncio
    async def test_fingerprints_in_serialized_detail_when_set(self) -> None:
        """Non-None fingerprints appear in to_detail() output."""
        project = _make_project_mock_for_publish()
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_project.return_value = project

        mock_tool_call_repo = AsyncMock()
        mock_tool_call_repo.get_tool_calls_by_conversation.return_value = []

        with (
            patch("db.session.AsyncSessionLocal") as mock_session_cls,
            patch(f"{VOICE_MODULE}.db") as mock_db,
            patch(
                f"{VOICE_MODULE}.ToolCallRecordRepositoryAsync"
            ) as mock_tool_call_repo_cls,
            patch(
                f"{VOICE_MODULE}.publish_event", new_callable=AsyncMock
            ) as mock_publish,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_db.ProjectRepositoryAsync.return_value = mock_repo
            mock_tool_call_repo_cls.return_value = mock_tool_call_repo
            mock_publish.return_value = True

            kwargs = _common_publish_kwargs(
                agent_fingerprint="deadbeef12345678",
                prompt_fingerprint="cafebabe87654321",
            )
            await _publish_livekit_evaluation_event(**kwargs)

        event = mock_publish.call_args[0][0]
        detail = event.to_detail()
        assert detail["agent_fingerprint"] == "deadbeef12345678"
        assert detail["prompt_fingerprint"] == "cafebabe87654321"
