import uuid
from unittest.mock import AsyncMock

import pytest

from agent import (
    AgentConfig,
    AgentMetadata,
    AgentPersona,
    KnowledgeConfig,
    LlamaIndexSettings,
    ModelConfig,
    ToolConfig,
    ToolMetadata,
    VectorStoreModality,
    VectorStoreProvider,
)
from db.tables.types import Channel
from services.agent_service import _implementation


def _build_agent_config() -> AgentConfig:
    return AgentConfig(
        persona=AgentPersona(
            name="Test Agent",
            role="assistant",
            description="You are a helpful assistant.",
        ),
        model=ModelConfig(),
        knowledge=KnowledgeConfig(
            enabled=True,
            identifier="test-knowledge",
            settings=LlamaIndexSettings(
                vector_store_provider=VectorStoreProvider.PINECONE,
                vector_store_modality=VectorStoreModality.TEXT,
                index_name="test-index",
                namespace="test-namespace",
            ),
        ),
        tool=ToolConfig(
            identifiers=[],
            metadata=ToolMetadata(
                agent_id=uuid.uuid4(),
                account_id=uuid.uuid4(),
                account_name="test-account",
                user_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
            ),
        ),
        metadata=AgentMetadata(
            account_name="test-account",
            agent_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
        ),
    )


@pytest.mark.parametrize(
    ("raw_config", "expected_size", "expected_priority"),
    [
        ({"model": "m"}, "m", False),
        ({"model": "L"}, "l", False),
        ({"model": "XM"}, "xm", False),
        ({"model": "xm"}, "xm", False),
        ({"model": "XM_AZURE"}, "xm_azure", False),
        ({"model": "mega"}, "m", False),
        ({"model": {"size": "m", "priority": True}}, "m", True),
        ({"model": {"size": "xm", "priority": True}}, "xm", True),
        ({"model": {"size": "xm_azure"}}, "xm_azure", False),
        ({"model": {"size": "xl"}}, "xl", False),
        ({"model": {"size": "huge", "priority": True}}, "m", True),
        ({"model": {"size": "m", "priority": "true"}}, "m", False),
        ({"model": {"size": "m", "priority": 1}}, "m", False),
        ({"model": {"size": "m", "priority": None}}, "m", False),
        ({}, "m", False),
        ({"model": None}, "m", False),
        ({"model": ["m"]}, "m", False),
        (None, "m", False),
    ],
)
@pytest.mark.asyncio
async def test_construct_agent_spec_parses_model_config(
    monkeypatch,
    raw_config,
    expected_size,
    expected_priority,
):
    mock_construct_agent_config = AsyncMock(return_value=_build_agent_config())
    monkeypatch.setattr(
        _implementation,
        "construct_agent_config",
        mock_construct_agent_config,
    )
    monkeypatch.setattr(
        _implementation,
        "_build_specs_from_project_integrations",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        _implementation,
        "_build_pal_tools_specs_from_project_integrations",
        AsyncMock(return_value=[]),
    )

    # Mock AgentRepositoryAsync to return agent with no language
    from unittest.mock import MagicMock

    mock_db_agent = MagicMock()
    mock_db_agent.language = None

    mock_agent_repo = AsyncMock()
    mock_agent_repo.get_agent = AsyncMock(return_value=mock_db_agent)
    monkeypatch.setattr(
        _implementation.db,
        "AgentRepositoryAsync",
        lambda session: mock_agent_repo,
    )

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config=raw_config,
    )

    assert spec.model.size == expected_size
    assert spec.model.priority is expected_priority
