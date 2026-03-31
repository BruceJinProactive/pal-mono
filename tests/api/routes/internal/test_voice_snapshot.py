"""Tests for agent config snapshot wiring in voice init (P1-E1)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.internal._voice import init_voice_call
from api.schemas.internal.voice_init import VoiceInitRequest, VoiceInitResponse
from db.tables.types import SpeechRate

VOICE_MODULE = "api.routes.internal._voice"


def _make_request(**overrides: str) -> VoiceInitRequest:
    defaults: dict[str, str] = {
        "caller_number": "+15551234567",
        "dialed_number": "+15559876543",
        "call_id": "call-snapshot-test",
    }
    defaults.update(overrides)
    return VoiceInitRequest(**defaults)


def _make_project(**overrides: object) -> MagicMock:
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


def _make_voice_config(**overrides: object) -> MagicMock:
    vc = MagicMock()
    vc.language = overrides.get("language", "english")
    vc.voice_id = overrides.get("voice_id", "voice-abc")
    vc.speech_rate = overrides.get("speech_rate", SpeechRate.normal)
    vc.first_message = overrides.get("first_message", "Hello!")
    vc.background_sound = overrides.get("background_sound", None)
    return vc


def _make_db_agent() -> MagicMock:
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.account = MagicMock()
    agent.account.id = uuid.uuid4()
    return agent


class TestSnapshotTaskFired:
    """Snapshot background task is created after fingerprint computation."""

    @pytest.mark.asyncio
    async def test_snapshot_task_fired_with_correct_args(self) -> None:
        project = _make_project()
        user = _make_user()
        vc = _make_voice_config()
        db_agent = _make_db_agent()
        mock_config = MagicMock()
        mock_config.persona.description = "You are a helpful bot."

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
            patch(
                f"{VOICE_MODULE}.upsert_agent_config_snapshot",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch(f"{VOICE_MODULE}.asyncio.create_task") as mock_create_task,
        ):
            mock_msg_cls.return_value = AsyncMock()

            vc_repo = AsyncMock()
            vc_repo.get_voice_configs_by_project.return_value = [vc]
            mock_vc_cls.return_value = vc_repo

            agent_repo = AsyncMock()
            agent_repo.get_agent = AsyncMock(return_value=db_agent)
            mock_agent_repo_cls.return_value = agent_repo

            config_dict = {"persona": {"name": "TestBot"}}
            mock_raw_config_instance = MagicMock()
            mock_raw_config_instance.build_with_fingerprint = AsyncMock(
                return_value=(
                    mock_config,
                    "aabbccddeeff0011",
                    "11223344aabbccdd",
                    config_dict,
                )
            )
            mock_raw_config_cls.return_value = mock_raw_config_instance

            conv_repo = AsyncMock()
            conv_repo.get_conversation_by_call_id = AsyncMock(
                return_value=mock_conversation
            )
            mock_conv_repo_cls.return_value = conv_repo

            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            result = await init_voice_call(_make_request(), session)

        assert isinstance(result, VoiceInitResponse)
        # upsert_agent_config_snapshot should have been passed to create_task
        mock_create_task.assert_called()
        # Verify upsert was called with correct coroutine args
        call_args = mock_upsert.call_args
        assert call_args.kwargs["fingerprint"] == "aabbccddeeff0011"
        assert call_args.kwargs["agent_id"] == db_agent.id
        assert call_args.kwargs["prompt_hash"] == "11223344aabbccdd"
        assert call_args.kwargs["prompt_text"] == "You are a helpful bot."

    @pytest.mark.asyncio
    async def test_init_succeeds_when_snapshot_fails(self) -> None:
        """Voice init must not fail even if snapshot upsert raises."""
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
            patch(
                f"{VOICE_MODULE}.upsert_agent_config_snapshot",
                new_callable=AsyncMock,
            ),
            patch(f"{VOICE_MODULE}.asyncio.create_task") as mock_create_task,
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
            conv_repo.get_conversation_by_call_id = AsyncMock(
                return_value=mock_conversation
            )
            mock_conv_repo_cls.return_value = conv_repo

            # Simulate background scheduling failure; init must still succeed.
            mock_create_task.side_effect = RuntimeError("task scheduling failed")

            result = await init_voice_call(_make_request(), session)

        assert isinstance(result, VoiceInitResponse)

    @pytest.mark.asyncio
    async def test_snapshot_not_fired_when_agent_not_found(self) -> None:
        """When agent lookup returns None, no snapshot task is created."""
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
            patch(
                f"{VOICE_MODULE}.upsert_agent_config_snapshot",
                new_callable=AsyncMock,
            ) as mock_upsert,
        ):
            mock_msg_cls.return_value = AsyncMock()

            vc_repo = AsyncMock()
            vc_repo.get_voice_configs_by_project.return_value = [vc]
            mock_vc_cls.return_value = vc_repo

            agent_repo = AsyncMock()
            agent_repo.get_agent = AsyncMock(return_value=None)
            mock_agent_repo_cls.return_value = agent_repo

            result = await init_voice_call(_make_request(), session)

        assert isinstance(result, VoiceInitResponse)
        mock_upsert.assert_not_called()
