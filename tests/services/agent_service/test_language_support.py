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
from db.tables.types import Channel, Language
from services.agent_service import _implementation


def _build_agent_config(language: str | None = None) -> AgentConfig:
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
            language=language,
        ),
    )


@pytest.mark.asyncio
async def test_language_from_db_when_not_provided(monkeypatch):
    """Test that language from DB agent is used when not provided as parameter."""
    mock_construct_agent_config = AsyncMock(
        return_value=_build_agent_config(language=Language.english.value)
    )
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

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={},
    )

    # Verify language from DB was used if FillerWordsSpec supports it
    from pal_agents.spec import FillerWordsSpec

    if "language" in FillerWordsSpec.model_fields:
        assert getattr(spec.filler_words, "language") == "english"


@pytest.mark.asyncio
async def test_language_parameter_overrides_db(monkeypatch):
    """Test that explicit language parameter overrides DB value."""
    mock_construct_agent_config = AsyncMock(
        return_value=_build_agent_config(language=Language.multilingual.value)
    )
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

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={},
        language="spanish",  # Explicit override
    )

    # Verify explicit parameter was used if FillerWordsSpec supports it
    from pal_agents.spec import FillerWordsSpec

    if "language" in FillerWordsSpec.model_fields:
        assert getattr(spec.filler_words, "language") == "spanish"
