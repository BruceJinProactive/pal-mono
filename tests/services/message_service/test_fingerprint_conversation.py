"""Tests for _fingerprint_conversation background task."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.tables.types import Channel


@pytest.fixture
def ids():
    return SimpleNamespace(
        agent=uuid.uuid4(),
        project=uuid.uuid4(),
        user=uuid.uuid4(),
        conversation=uuid.uuid4(),
    )


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture
def mock_conversation():
    conv = MagicMock()
    conv.agent_fingerprint = None
    conv.prompt_fingerprint = None
    return conv


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.account = MagicMock()
    return agent


@pytest.fixture
def mock_project():
    return MagicMock()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.persona.description = "You are a helpful restaurant assistant."
    return config


@pytest.mark.asyncio
async def test_fingerprints_conversation_on_first_message(
    ids, mock_session, mock_conversation, mock_agent, mock_project, mock_config
):
    agent_fp = "a" * 64
    prompt_fp = "b" * 64
    config_dict = {"agent_id": str(ids.agent)}

    mock_raw_config_instance = AsyncMock()
    mock_raw_config_instance.build_with_fingerprint = AsyncMock(
        return_value=(mock_config, agent_fp, prompt_fp, config_dict)
    )

    mock_conv_repo = AsyncMock()
    mock_conv_repo.get_conversation_by_id = AsyncMock(return_value=mock_conversation)

    mock_agent_repo = AsyncMock()
    mock_agent_repo.get_agent = AsyncMock(return_value=mock_agent)

    mock_project_repo = AsyncMock()
    mock_project_repo.get_project = AsyncMock(return_value=mock_project)

    with (
        patch(
            "services.message_service._implementation.AsyncSessionLocal",
            return_value=mock_session,
        ),
        patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=mock_conv_repo,
        ),
        patch(
            "services.message_service._implementation.db.AgentRepositoryAsync",
            return_value=mock_agent_repo,
        ),
        patch(
            "services.message_service._implementation.db.ProjectRepositoryAsync",
            return_value=mock_project_repo,
        ),
        patch(
            "services.agent_service._raw_config.RawConfig",
            return_value=mock_raw_config_instance,
        ),
        patch(
            "services.eval_service._snapshot.upsert_agent_config_snapshot",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        from services.message_service._implementation import _fingerprint_conversation

        await _fingerprint_conversation(
            agent_id=ids.agent,
            project_id=ids.project,
            user_id=ids.user,
            conversation_id=ids.conversation,
            channel=Channel.API,
        )

    assert mock_conversation.agent_fingerprint == agent_fp
    assert mock_conversation.prompt_fingerprint == prompt_fp
    mock_session.commit.assert_awaited_once()
    mock_upsert.assert_awaited_once_with(
        fingerprint=agent_fp,
        agent_id=ids.agent,
        project_id=ids.project,
        config_dict=config_dict,
        prompt_hash=prompt_fp,
        prompt_text="You are a helpful restaurant assistant.",
    )


@pytest.mark.asyncio
async def test_skips_already_fingerprinted(ids, mock_session):
    conv = MagicMock()
    conv.agent_fingerprint = "already_set"

    mock_conv_repo = AsyncMock()
    mock_conv_repo.get_conversation_by_id = AsyncMock(return_value=conv)

    with (
        patch(
            "services.message_service._implementation.AsyncSessionLocal",
            return_value=mock_session,
        ),
        patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=mock_conv_repo,
        ),
        patch(
            "services.message_service._implementation.db.AgentRepositoryAsync",
        ) as mock_agent_cls,
    ):
        from services.message_service._implementation import _fingerprint_conversation

        await _fingerprint_conversation(
            agent_id=ids.agent,
            project_id=ids.project,
            user_id=ids.user,
            conversation_id=ids.conversation,
            channel=Channel.API,
        )

    mock_agent_cls.assert_not_called()
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_when_agent_not_found(ids, mock_session, mock_conversation):
    mock_conv_repo = AsyncMock()
    mock_conv_repo.get_conversation_by_id = AsyncMock(return_value=mock_conversation)

    mock_agent_repo = AsyncMock()
    mock_agent_repo.get_agent = AsyncMock(return_value=None)

    with (
        patch(
            "services.message_service._implementation.AsyncSessionLocal",
            return_value=mock_session,
        ),
        patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=mock_conv_repo,
        ),
        patch(
            "services.message_service._implementation.db.AgentRepositoryAsync",
            return_value=mock_agent_repo,
        ),
    ):
        from services.message_service._implementation import _fingerprint_conversation

        await _fingerprint_conversation(
            agent_id=ids.agent,
            project_id=ids.project,
            user_id=ids.user,
            conversation_id=ids.conversation,
            channel=Channel.API,
        )

    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_when_project_not_found(
    ids, mock_session, mock_conversation, mock_agent
):
    mock_conv_repo = AsyncMock()
    mock_conv_repo.get_conversation_by_id = AsyncMock(return_value=mock_conversation)

    mock_agent_repo = AsyncMock()
    mock_agent_repo.get_agent = AsyncMock(return_value=mock_agent)

    mock_project_repo = AsyncMock()
    mock_project_repo.get_project = AsyncMock(return_value=None)

    with (
        patch(
            "services.message_service._implementation.AsyncSessionLocal",
            return_value=mock_session,
        ),
        patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=mock_conv_repo,
        ),
        patch(
            "services.message_service._implementation.db.AgentRepositoryAsync",
            return_value=mock_agent_repo,
        ),
        patch(
            "services.message_service._implementation.db.ProjectRepositoryAsync",
            return_value=mock_project_repo,
        ),
    ):
        from services.message_service._implementation import _fingerprint_conversation

        await _fingerprint_conversation(
            agent_id=ids.agent,
            project_id=ids.project,
            user_id=ids.user,
            conversation_id=ids.conversation,
            channel=Channel.API,
        )

    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_swallows_exceptions(ids):
    with patch(
        "services.message_service._implementation.AsyncSessionLocal",
        side_effect=RuntimeError("db down"),
    ):
        from services.message_service._implementation import _fingerprint_conversation

        # Should not raise
        await _fingerprint_conversation(
            agent_id=ids.agent,
            project_id=ids.project,
            user_id=ids.user,
            conversation_id=ids.conversation,
            channel=Channel.API,
        )
