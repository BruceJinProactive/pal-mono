import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pal_agents.providers.olo import Olo
from pal_agents.spec import OloSpec
from pydantic import ValidationError

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
from services.agent_service._implementation import (
    _build_specs_from_project_integrations,
)
from services.agent_service._pal_agent_tool_registry import PAL_AGENT_TOOL_REGISTRY


def _make_project_integration(
    *,
    tool_name: str = "olo_v1",
    store_identifier: str = "3569",
    config: dict[str, Any] | None = None,
    integration_id: uuid.UUID | None = None,
) -> MagicMock:
    pi = MagicMock()
    pi.id = uuid.uuid4()
    pi.tool_name = tool_name
    pi.store_identifier = store_identifier
    pi.config = config or {}
    pi.integration_id = integration_id or uuid.uuid4()
    return pi


def _make_integration_record(
    *,
    client_id: str = "olo-client-id",
    client_secret: str = "olo-client-secret",
    secret_key: str | None = None,
) -> MagicMock:
    record = MagicMock()
    record.id = uuid.uuid4()
    record.client_id = client_id
    record.client_secret = client_secret
    record.secret_key = secret_key
    return record


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


def _compiled_olo_menu_data() -> dict[str, Any]:
    return {
        "version": 1,
        "restaurant_id": "3569",
        "items": [
            {
                "product_id": 100,
                "item_name": "Cheeseburger",
                "normalized_item_name": "cheeseburger",
                "category_id": 10,
                "category_name": "Burgers",
                "description": "Burger with cheese",
                "cost": 8.99,
                "minimum_quantity": None,
                "maximum_quantity": None,
                "quantity_increment": None,
                "has_consolidated_quantities": None,
                "root_modifier_group_ids": [],
            }
        ],
        "modifier_groups_by_id": {},
        "modifier_options_by_id": {},
        "option_paths_by_product_id": {"100": []},
    }


def test_registry_builds_olo_v1_spec_from_project_integration_config() -> None:
    builder = PAL_AGENT_TOOL_REGISTRY["olo_v1"].builder
    config = {
        "menu_data": _compiled_olo_menu_data(),
        "base_url": "https://ordering.api.olo.com",
        "auth": {"type": "signature"},
        "timeout": 15.0,
        "debug": True,
        "lookup_tool_name": "lookup_olo_order_options_v1",
        "tool_name": "olo_create_order_v1",
    }

    result = builder(config, "3569", "client-id", "client-secret", None)

    assert isinstance(result, OloSpec)
    assert result.enabled is True
    assert result.menu_data == _compiled_olo_menu_data()
    assert result.restaurant_id == 3569
    assert result.base_url == "https://ordering.api.olo.com"
    assert result.timeout == 15.0
    assert result.debug is True
    assert result.lookup_tool_name == "lookup_olo_order_options_v1"
    assert result.tool_name == "olo_create_order_v1"
    assert result.auth == {
        "type": "signature",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }


def test_registry_rejects_olo_v1_without_menu_data() -> None:
    builder = PAL_AGENT_TOOL_REGISTRY["olo_v1"].builder

    with pytest.raises(ValidationError, match="menu_data required when olo is enabled"):
        builder({}, "3569", "client-id", "client-secret", None)


def test_olo_v1_spec_exposes_lookup_and_create_order_tools() -> None:
    builder = PAL_AGENT_TOOL_REGISTRY["olo_v1"].builder
    spec = builder(
        {
            "menu_data": _compiled_olo_menu_data(),
            "base_url": "https://ordering.api.olo.com",
            "auth": {"type": "signature"},
        },
        "3569",
        "client-id",
        "client-secret",
        None,
    )

    tools = Olo(spec).as_tool()

    assert isinstance(tools, list)
    assert [tool["name"] for tool in tools] == [
        "lookup_olo_order_options_v1",
        "olo_create_order_v1",
    ]


@pytest.mark.asyncio
async def test_build_specs_from_project_integrations_dispatches_olo_v1() -> None:
    pi = _make_project_integration(
        config={
            "menu_data": _compiled_olo_menu_data(),
            "auth": {"type": "signature"},
        },
    )
    integration_record = _make_integration_record(
        client_id="real-client-id",
        client_secret="real-client-secret",
        secret_key=None,
    )

    session = AsyncMock()
    pi_result = MagicMock()
    pi_result.scalars.return_value = iter([pi])
    int_result = MagicMock()
    int_result.scalar_one_or_none.return_value = integration_record
    session.execute = AsyncMock(side_effect=[pi_result, int_result])

    result = await _build_specs_from_project_integrations(session, uuid.uuid4())

    assert "olo" in result
    spec = result["olo"]
    assert isinstance(spec, OloSpec)
    assert spec.enabled is True
    assert spec.restaurant_id == 3569
    assert spec.auth == {
        "type": "signature",
        "client_id": "real-client-id",
        "client_secret": "real-client-secret",
    }


@pytest.mark.asyncio
async def test_construct_agent_spec_threads_olo_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                "olo": OloSpec(
                    enabled=True,
                    menu_data=_compiled_olo_menu_data(),
                    restaurant_id=3569,
                    base_url="https://ordering.api.olo.com",
                    auth={
                        "type": "signature",
                        "client_id": "cid",
                        "client_secret": "secret",
                    },
                )
            }
        ),
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

    assert spec.olo.enabled is True
    assert spec.olo.restaurant_id == 3569
    assert spec.olo.base_url == "https://ordering.api.olo.com"

    tools = Olo(spec.olo).as_tool()
    assert isinstance(tools, list)
    assert [tool["name"] for tool in tools] == [
        "lookup_olo_order_options_v1",
        "olo_create_order_v1",
    ]
