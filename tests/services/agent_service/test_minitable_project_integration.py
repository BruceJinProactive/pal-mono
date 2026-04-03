import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pal_agents.spec import ToolSpec

from services.agent_service import _implementation
from services.agent_service._implementation import (
    _build_pal_tools_specs_from_project_integrations,
)


def _make_project_integration(
    *,
    tool_name: str = "minitable_tool",
    store_identifier: str = "12345",
    config: dict | None = None,
    integration_id: uuid.UUID | None = None,
):
    pi = MagicMock()
    pi.tool_name = tool_name
    pi.store_identifier = store_identifier
    pi.config = config or {}
    pi.integration_id = integration_id or uuid.uuid4()
    return pi


class TestBuildPalToolsSpecsFromProjectIntegrations:
    @pytest.mark.asyncio
    async def test_builds_minitable_toolkit_spec(self, monkeypatch):
        pi = _make_project_integration(
            tool_name="minitable_tool",
            store_identifier="12345",
        )

        session = AsyncMock()
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([pi])
        int_result = MagicMock()
        int_result.scalar_one_or_none.return_value = MagicMock()
        session.execute = AsyncMock(side_effect=[pi_result, int_result])

        monkeypatch.setattr(
            _implementation,
            "_resolve_integration_credentials",
            AsyncMock(return_value=("mt-user", "mt-pass", None)),
        )

        result = await _build_pal_tools_specs_from_project_integrations(
            session, uuid.uuid4()
        )

        assert len(result) == 1
        spec = result[0]
        assert isinstance(spec, ToolSpec)
        assert spec.tool_name == "MiniTableToolkit"
        assert spec.config == {
            "username": "mt-user",
            "password": "mt-pass",
            "restaurant_id": "12345",
        }

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_integrations(self):
        session = AsyncMock()
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([])
        session.execute = AsyncMock(return_value=pi_result)

        result = await _build_pal_tools_specs_from_project_integrations(
            session, uuid.uuid4()
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_unknown_tool_names(self):
        pi = _make_project_integration(tool_name="unknown_tool")
        session = AsyncMock()
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([pi])
        session.execute = AsyncMock(return_value=pi_result)

        result = await _build_pal_tools_specs_from_project_integrations(
            session, uuid.uuid4()
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_handles_none_credentials(self, monkeypatch):
        pi = _make_project_integration()

        session = AsyncMock()
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([pi])
        int_result = MagicMock()
        int_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[pi_result, int_result])

        monkeypatch.setattr(
            _implementation,
            "_resolve_integration_credentials",
            AsyncMock(return_value=(None, None, None)),
        )

        result = await _build_pal_tools_specs_from_project_integrations(
            session, uuid.uuid4()
        )

        assert len(result) == 1
        assert result[0].config["username"] == ""
        assert result[0].config["password"] == ""
