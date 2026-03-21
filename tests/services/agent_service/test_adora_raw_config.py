import uuid
from unittest.mock import AsyncMock

import pytest
from pal_agents.spec import AdoraSpec

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
from services.agent_service._implementation import _build_adora_spec_from_raw_config

MENU_DATA = {"version": 1, "items": {}}
LOOKUP_MENU_DATA = {
    "version": "adora_llm_menu_v9",
    "group_templates": {},
    "modifier_templates": {},
    "items": [],
}


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


def test_build_adora_spec_from_raw_config_ignores_lookup_menu_data():
    raw_config = {
        "adora": {
            "enabled": True,
            "menu_data": MENU_DATA,
            "lookup_menu_data": LOOKUP_MENU_DATA,
        }
    }

    spec = _build_adora_spec_from_raw_config(raw_config)

    assert spec.enabled is True
    assert spec.menu_data == MENU_DATA
    assert not hasattr(spec, "lookup_menu_data")


@pytest.mark.asyncio
async def test_construct_agent_spec_builds_adora_from_raw_config(monkeypatch):
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

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={
            "adora": {
                "enabled": True,
                "menu_data": MENU_DATA,
            }
        },
    )

    assert spec.adora.enabled is True
    assert spec.adora.menu_data == MENU_DATA


@pytest.mark.asyncio
async def test_construct_agent_spec_prefers_project_integration_adora_spec(
    monkeypatch,
):
    monkeypatch.setattr(
        _implementation,
        "construct_agent_config",
        AsyncMock(return_value=_build_agent_config()),
    )
    monkeypatch.setattr(
        _implementation,
        "_build_specs_from_project_integrations",
        AsyncMock(
            return_value={
                "adora": AdoraSpec(
                    enabled=True,
                    menu_data=MENU_DATA,
                    base_url="https://public.api.adorapos.net",
                    store_id="UGDX4",
                )
            }
        ),
    )

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={
            "adora": {
                "enabled": True,
                "lookup_menu_data": LOOKUP_MENU_DATA,
            }
        },
    )

    assert spec.adora.enabled is True
    assert spec.adora.menu_data == MENU_DATA
    assert spec.adora.store_id == "UGDX4"
    assert not hasattr(spec.adora, "lookup_menu_data")
