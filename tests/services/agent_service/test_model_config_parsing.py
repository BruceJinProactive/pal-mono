import uuid
from unittest.mock import AsyncMock

import pytest

from agent import (
    AgentConfig,
    AgentMetadata,
    AgentPersona,
    KnowledgeConfig,
    LlamaIndexSettings,
    MemoryConfig,
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
        memory=MemoryConfig(enabled=True, identifier="test-memory"),
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
        ({"model": "mega"}, "m", False),
        ({"model": {"size": "m", "priority": True}}, "m", True),
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
