"""Tests for Olo project integration admin behavior."""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin._integration import (
    _build_olo_product_info,
    _build_olo_product_info_or_400,
    _update_project_product_info,
    create_project_integration,
    update_project_integration,
)
from api.schemas.admin.integration import (
    CreateProjectIntegrationRequest,
    UpdateProjectIntegrationRequest,
)
from services.integration_service.schema import ProjectIntegrationParams


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.username = str(uuid.uuid4())
    return ctx


def _mock_sync_session(integration: SimpleNamespace | None) -> MagicMock:
    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = integration
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_session)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def test_build_olo_product_info_handles_missing_menu_data() -> None:
    assert _build_olo_product_info(None) is None
    assert _build_olo_product_info({}) is None
    assert _build_olo_product_info({"menu_data": []}) is None


def test_build_olo_product_info_error_is_400() -> None:
    with pytest.raises(HTTPException) as exc:
        _build_olo_product_info_or_400(
            uuid.uuid4(),
            {"menu_data": {"items": [], "modifier_groups_by_id": []}},
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Failed to build Olo product info"


def test_update_project_product_info_skips_empty_and_raises_not_found() -> None:
    repo = MagicMock()

    _update_project_product_info(repo, uuid.uuid4(), None)
    _update_project_product_info(repo, uuid.uuid4(), "")

    repo.update_project.assert_not_called()

    repo.update_project.return_value = None
    with pytest.raises(HTTPException) as exc:
        _update_project_product_info(repo, uuid.uuid4(), "## menu")

    assert exc.value.status_code == 404


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
        "items": [
            {
                "item_name": "Classic Burger",
                "category_name": "Burgers",
                "root_modifier_group_ids": [200],
            },
            {
                "item_name": "Vanilla Shake",
                "category_name": "Shakes",
                "root_modifier_group_ids": [],
            },
        ],
        "modifier_groups_by_id": {
            "200": {
                "name": "Would you like to make it a combo?",
                "required": True,
                "default_option_ids": [300],
            }
        },
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
    write_order: list[str] = []

    def _update_project_integration(
        *,
        params: ProjectIntegrationParams,
        **_kwargs: object,
    ) -> SimpleNamespace:
        write_order.append("integration")
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
        repo_cls.return_value.update_project.side_effect = lambda *_args, **_kwargs: (
            write_order.append("project") or SimpleNamespace(id=project_id)
        )

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
    assert write_order == ["integration", "project"]
    repo_cls.return_value.update_project.assert_called_once()
    product_info = repo_cls.return_value.update_project.call_args.kwargs["product_info"]
    assert "## Exact Item Inventory" in product_info
    assert "### Burgers" in product_info
    assert "- Classic Burger" in product_info
    assert (
        "- Classic Burger -> Would you like to make it a combo? "
        "[selection_state=auto_selected]"
    ) in product_info


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


@pytest.mark.asyncio
async def test_create_project_integration_auto_fetches_olo_menu_data() -> None:
    project_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    account_id = uuid.uuid4()
    session = MagicMock()
    compiled_menu = {
        "version": 1,
        "restaurant_id": "259950",
        "items": [
            {
                "item_name": "Classic Burger",
                "category_name": "Burgers",
                "root_modifier_group_ids": [200],
            },
            {
                "item_name": "Vanilla Shake",
                "category_name": "Shakes",
                "root_modifier_group_ids": [],
            },
        ],
        "modifier_groups_by_id": {
            "200": {
                "name": "Would you like to make it a combo?",
                "required": True,
                "default_option_ids": [300],
            }
        },
    }
    req = CreateProjectIntegrationRequest(
        integration_id=integration_id,
        store_identifier="259950",
        tool_name="olo_v1",
        config={"restaurant_id": "259950"},
        auto_fetch=True,
    )
    integration = SimpleNamespace(
        id=integration_id,
        account_id=account_id,
        secret_key="olo-secret",
        raw_config={
            "api_endpoints": {
                "general_api_endpoint": "https://ordering.api.olo.com",
            },
        },
    )
    write_order: list[str] = []

    def _create_project_integration(
        *,
        params: ProjectIntegrationParams,
        **_kwargs: object,
    ) -> SimpleNamespace:
        write_order.append("integration")
        return SimpleNamespace(
            id=uuid.uuid4(),
            project_id=project_id,
            integration_id=integration_id,
            store_identifier=params.store_identifier,
            tool_name=params.tool_name,
            config=params.config,
            created_at=datetime.now(),
        )

    with (
        patch("api.routes.admin._integration.db.ProjectRepository") as repo_cls,
        patch(
            "db.session.SyncSessionLocal",
            return_value=_mock_sync_session(integration),
        ),
        patch(
            "api.routes.admin._integration._get_integration_credentials",
            return_value={"client_id": "cid", "client_secret": "secret"},
        ),
        patch(
            "api.routes.admin._integration.fetch_and_compile_olo_menu_data",
            return_value=compiled_menu,
        ) as mock_fetch_and_compile,
        patch(
            "api.routes.admin._integration.integration_service.create_project_integration",
            side_effect=_create_project_integration,
        ) as mock_create,
    ):
        repo_cls.return_value.get_project.return_value = SimpleNamespace(
            id=project_id,
            account_id=account_id,
        )
        repo_cls.return_value.update_project.side_effect = lambda *_args, **_kwargs: (
            write_order.append("project") or SimpleNamespace(id=project_id)
        )

        result = await create_project_integration(
            project_id,
            req,
            _make_context(),
            session,
        )

    mock_fetch_and_compile.assert_called_once_with(
        restaurant_id="259950",
        client_id="cid",
        client_secret="secret",
        general_api_endpoint="https://ordering.api.olo.com",
        selected_categories=None,
        make_unique_categories=None,
    )
    params = mock_create.call_args.kwargs["params"]
    assert params.config["menu_data"] == compiled_menu
    assert params.config["menu_last_updated_source"] == "manage_app"
    assert result.config["menu_data"] == compiled_menu
    assert write_order == ["integration", "project"]
    repo_cls.return_value.update_project.assert_called_once()
    product_info = repo_cls.return_value.update_project.call_args.kwargs["product_info"]
    assert "## Exact Item Inventory" in product_info
    assert "### Burgers" in product_info
    assert "- Classic Burger" in product_info
    assert (
        "- Classic Burger -> Would you like to make it a combo? "
        "[selection_state=auto_selected]"
    ) in product_info


@pytest.mark.asyncio
async def test_update_project_integration_auto_fetches_olo_menu_data() -> None:
    project_id = uuid.uuid4()
    project_integration_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    account_id = uuid.uuid4()
    session = MagicMock()
    compiled_menu = {
        "version": 1,
        "restaurant_id": "259950",
        "items": [
            {
                "item_name": "Classic Burger",
                "category_name": "Burgers",
                "root_modifier_group_ids": [200],
            },
            {
                "item_name": "Vanilla Shake",
                "category_name": "Shakes",
                "root_modifier_group_ids": [],
            },
        ],
        "modifier_groups_by_id": {
            "200": {
                "name": "Would you like to make it a combo?",
                "required": True,
                "default_option_ids": [300],
            }
        },
    }
    req = UpdateProjectIntegrationRequest(
        config={
            "restaurant_id": "259950",
            "base_url": "https://ordering.api.olo.com",
            "auto_fetch_menu_data": True,
        },
    )
    db_project_integration = SimpleNamespace(
        id=project_integration_id,
        project_id=project_id,
        integration_id=integration_id,
        store_identifier="259950",
        tool_name="olo_v1",
        config={"handoff_enabled": True, "menu_data": {"items": [{"old": True}]}},
        created_at=datetime.now(),
    )
    integration = SimpleNamespace(
        id=integration_id,
        account_id=account_id,
        secret_key="olo-secret",
        raw_config={},
    )
    write_order: list[str] = []

    def _update_project_integration(
        *,
        params: ProjectIntegrationParams,
        **_kwargs: object,
    ) -> SimpleNamespace:
        write_order.append("integration")
        return SimpleNamespace(
            id=project_integration_id,
            project_id=project_id,
            integration_id=integration_id,
            store_identifier=params.store_identifier,
            tool_name="olo_v1",
            config=params.config,
            created_at=datetime.now(),
        )

    with (
        patch("api.routes.admin._integration.db.ProjectRepository") as repo_cls,
        patch(
            "db.session.SyncSessionLocal",
            return_value=_mock_sync_session(integration),
        ),
        patch(
            "api.routes.admin._integration.integration_service.get_project_integration_by_id",
            return_value=db_project_integration,
        ),
        patch(
            "api.routes.admin._integration.integration_service.update_project_integration",
            side_effect=_update_project_integration,
        ) as mock_update,
        patch(
            "api.routes.admin._integration._get_integration_credentials",
            return_value={"client_id": "cid", "client_secret": "secret"},
        ),
        patch(
            "api.routes.admin._integration.fetch_and_compile_olo_menu_data",
            return_value=compiled_menu,
        ) as mock_fetch_and_compile,
    ):
        repo_cls.return_value.get_project.return_value = SimpleNamespace(
            id=project_id,
            account_id=account_id,
        )
        repo_cls.return_value.update_project.side_effect = lambda *_args, **_kwargs: (
            write_order.append("project") or SimpleNamespace(id=project_id)
        )

        result = await update_project_integration(
            project_id,
            project_integration_id,
            req,
            _make_context(),
            session,
        )

    mock_fetch_and_compile.assert_called_once_with(
        restaurant_id="259950",
        client_id="cid",
        client_secret="secret",
        general_api_endpoint="https://ordering.api.olo.com",
        selected_categories=None,
        make_unique_categories=None,
    )
    params = mock_update.call_args.kwargs["params"]
    assert params.config["handoff_enabled"] is True
    assert params.config["menu_data"] == compiled_menu
    assert params.config["menu_last_updated_source"] == "manage_app"
    assert result.config["menu_data"] == compiled_menu
    assert write_order == ["integration", "project"]
    repo_cls.return_value.update_project.assert_called_once()
    product_info = repo_cls.return_value.update_project.call_args.kwargs["product_info"]
    assert "## Exact Item Inventory" in product_info
    assert "### Burgers" in product_info
    assert "- Classic Burger" in product_info
    assert (
        "- Classic Burger -> Would you like to make it a combo? "
        "[selection_state=auto_selected]"
    ) in product_info
