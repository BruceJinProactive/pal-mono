"""Tests for Olo project integration admin behavior."""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin._integration import update_project_integration
from api.schemas.admin.integration import UpdateProjectIntegrationRequest
from services.integration_service.schema import ProjectIntegrationParams


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.username = str(uuid.uuid4())
    return ctx


@pytest.mark.asyncio
async def test_update_project_integration_compiles_olo_raw_bundle_into_menu_data() -> (
    None
):
    project_id = uuid.uuid4()
    project_integration_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    session = MagicMock()
    raw_bundle = {
        "restaurant_id": "259950",
        "menu": {"categories": []},
        "modifiers_by_product_id": {},
    }
    compiled_menu = {
        "version": 1,
        "restaurant_id": "259950",
        "items": [],
    }
    existing_config = {
        "auth": {"token_url": "https://auth.example.com"},
        "handoff_enabled": True,
        "menu_data": {"items": [{"item_name": "old"}]},
    }
    req = UpdateProjectIntegrationRequest(
        config={
            "raw_menu_bundle": raw_bundle,
            "selected_categories": ["Burgers"],
            "make_unique_categories": ["Burgers"],
        },
    )
    db_project_integration = SimpleNamespace(
        id=project_integration_id,
        project_id=project_id,
        integration_id=integration_id,
        store_identifier="259950",
        tool_name="olo_v1",
        config=existing_config,
        created_at=datetime.now(),
    )

    def _update_project_integration(
        *,
        params: ProjectIntegrationParams,
        **_kwargs: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=project_integration_id,
            project_id=project_id,
            integration_id=integration_id,
            store_identifier="259950",
            tool_name="olo_v1",
            config=params.config,
            created_at=datetime.now(),
        )

    with (
        patch("api.routes.admin._integration.db.ProjectRepository") as repo_cls,
        patch(
            "api.routes.admin._integration.integration_service.get_project_integration_by_id",
            return_value=db_project_integration,
        ),
        patch(
            "api.routes.admin._integration.integration_service.update_project_integration",
            side_effect=_update_project_integration,
        ) as mock_update,
        patch(
            "api.routes.admin._integration.compile_olo_menu_data",
            return_value=compiled_menu,
        ) as mock_compile,
    ):
        repo_cls.return_value.get_project.return_value = SimpleNamespace(id=project_id)

        result = await update_project_integration(
            project_id,
            project_integration_id,
            req,
            _make_context(),
            session,
        )

    mock_compile.assert_called_once_with(
        raw_bundle,
        selected_categories=["Burgers"],
        make_unique_categories=["Burgers"],
    )
    params = mock_update.call_args.kwargs["params"]
    assert params.config["auth"] == {"token_url": "https://auth.example.com"}
    assert params.config["handoff_enabled"] is True
    assert params.config["menu_data"] == compiled_menu
    assert "raw_menu_bundle" not in params.config
    assert params.config["menu_last_updated_source"] == "manage_app"
    datetime.fromisoformat(params.config["menu_last_updated"])
    assert result.config["menu_data"] == compiled_menu


@pytest.mark.asyncio
async def test_update_project_integration_rejects_malformed_olo_raw_bundle() -> None:
    project_id = uuid.uuid4()
    project_integration_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    session = MagicMock()
    req = UpdateProjectIntegrationRequest(config={"raw_menu_bundle": ["not", "a dict"]})
    db_project_integration = SimpleNamespace(
        id=project_integration_id,
        project_id=project_id,
        integration_id=integration_id,
        store_identifier="259950",
        tool_name="olo_v1",
        config={},
        created_at=datetime.now(),
    )

    with (
        patch("api.routes.admin._integration.db.ProjectRepository") as repo_cls,
        patch(
            "api.routes.admin._integration.integration_service.get_project_integration_by_id",
            return_value=db_project_integration,
        ),
    ):
        repo_cls.return_value.get_project.return_value = SimpleNamespace(id=project_id)

        with pytest.raises(HTTPException) as exc:
            await update_project_integration(
                project_id,
                project_integration_id,
                req,
                _make_context(),
                session,
            )

    assert exc.value.status_code == 400
    assert "raw_menu_bundle" in exc.value.detail
