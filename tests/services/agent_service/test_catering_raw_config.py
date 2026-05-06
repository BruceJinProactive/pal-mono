"""Tests for catering raw_config parsing and Spec construction."""

import uuid
from unittest.mock import AsyncMock

import pytest
from pal_agents.spec import Spec

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
from services.agent_service._implementation import _is_catering_enabled


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


class TestIsCateringEnabled:
    """Tests for _is_catering_enabled."""

    def test_empty_raw_config(self):
        assert _is_catering_enabled({}) is False

    def test_no_tools_section(self):
        assert _is_catering_enabled({"adora": {}}) is False

    def test_tools_empty_identifiers(self):
        assert _is_catering_enabled({"tools": {"identifiers": []}}) is False

    def test_other_tools_only(self):
        raw_config = {
            "tools": {
                "identifiers": [
                    {"tool_name": "vapi_tool", "tool_args": {}, "access_metadata": 1}
                ]
            }
        }
        assert _is_catering_enabled(raw_config) is False

    def test_catering_enabled(self):
        raw_config = {
            "tools": {
                "identifiers": [
                    {
                        "tool_name": "catering_tool",
                        "tool_args": {},
                        "access_metadata": 1,
                    }
                ]
            }
        }
        assert _is_catering_enabled(raw_config) is True

    def test_catering_enabled_among_other_tools(self):
        raw_config = {
            "tools": {
                "identifiers": [
                    {"tool_name": "vapi_tool", "tool_args": {}, "access_metadata": 1},
                    {
                        "tool_name": "catering_tool",
                        "tool_args": {},
                        "access_metadata": 1,
                    },
                ]
            }
        }
        assert _is_catering_enabled(raw_config) is True


_HAS_CATERING_FIELDS = "catering_enabled" in Spec.model_fields


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _HAS_CATERING_FIELDS,
    reason="pal-agents Spec missing catering fields — needs release with catering support",
)
async def test_construct_agent_spec_builds_catering_from_raw_config(monkeypatch):
    monkeypatch.setattr(
        _implementation,
        "construct_agent_config",
        AsyncMock(return_value=_build_agent_config()),
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

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={
            "tools": {
                "identifiers": [
                    {
                        "tool_name": "catering_tool",
                        "tool_args": {},
                        "access_metadata": 1,
                    }
                ]
            }
        },
    )

    assert getattr(spec, "catering_enabled") is True


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _HAS_CATERING_FIELDS,
    reason="pal-agents Spec missing catering fields — needs release with catering support",
)
async def test_construct_agent_spec_catering_disabled_by_default(monkeypatch):
    monkeypatch.setattr(
        _implementation,
        "construct_agent_config",
        AsyncMock(return_value=_build_agent_config()),
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

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={},
    )

    assert getattr(spec, "catering_enabled") is False
