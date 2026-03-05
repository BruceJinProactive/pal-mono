"""Tests for Adora V3 menu updater internals."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.internal._implementation import start_knowledge_update_process
from api.routes.internal.projects import update_knowledge
from db.tables.types import IntegrationProvider, IntegrationType
from services.adora_v3_menu_service import AdoraV3MenuAssets

DISCOVERY_BASE = "api.routes.internal._implementation"
PROJECTS_BASE = "api.routes.internal.projects"


def _make_project(**overrides):
    project = MagicMock()
    project.id = overrides.get("id", uuid.uuid4())
    project.account_id = overrides.get("account_id", uuid.uuid4())
    project.name = overrides.get("name", "Test Store")
    project.raw_config = overrides.get("raw_config", {})
    project.account = overrides.get("account")
    return project


def _make_account(**overrides):
    account = MagicMock()
    account.id = overrides.get("id", uuid.uuid4())
    return account


def _make_project_integration(**overrides):
    pi = MagicMock()
    pi.id = overrides.get("id", uuid.uuid4())
    pi.integration_id = overrides.get("integration_id", uuid.uuid4())
    pi.project_id = overrides.get("project_id", uuid.uuid4())
    pi.store_identifier = overrides.get("store_identifier", "UGDX4")
    pi.tool_name = overrides.get("tool_name", "adora_v3")
    pi.config = overrides.get("config", {"base_url": "https://public.api.adorapos.net"})
    return pi


def _make_integration(**overrides):
    integration = MagicMock()
    integration.id = overrides.get("id", uuid.uuid4())
    integration.secret_key = overrides.get("secret_key", "adora-secret")
    integration.raw_config = overrides.get(
        "raw_config",
        {
            "api_endpoints": {
                "token_api_endpoint": "https://identity.adorapos.net/connect/token",
                "general_api_endpoint": "https://public.api.adorapos.net/api/v1/OrderHub",
            }
        },
    )
    integration.integration_type = overrides.get(
        "integration_type", IntegrationType.pos
    )
    integration.provider = overrides.get("provider", IntegrationProvider.adora)
    return integration


@pytest.mark.asyncio
async def test_start_knowledge_update_process_discovers_adora_v3_without_legacy_raw_config():
    account = _make_account()
    project = _make_project(account=account, raw_config={})
    integration = _make_integration()
    integration.id = uuid.uuid4()
    pi = _make_project_integration(
        integration_id=integration.id,
        project_id=project.id,
        tool_name="adora_v3",
    )

    session = MagicMock()
    query = session.query.return_value
    query.join.return_value = query
    query.options.return_value = query
    query.filter.return_value = query
    query.all.return_value = [(pi, integration, project)]

    with (
        patch(
            f"{DISCOVERY_BASE}.publish_event", new_callable=AsyncMock
        ) as mock_publish,
        patch(f"{DISCOVERY_BASE}.SAFE_MODE", False),
    ):
        mock_publish.return_value = True
        result = await start_knowledge_update_process(session)

    assert result["events_published"] == 1
    event = mock_publish.call_args[0][0]
    assert event.project_id == project.id
    assert event.integration_id == integration.id
    assert event.project_integration_id == pi.id


@pytest.mark.asyncio
async def test_update_knowledge_writes_product_info_and_menu_data():
    project_id = uuid.uuid4()
    account_id = uuid.uuid4()
    project = _make_project(id=project_id, account_id=account_id)
    adora_pi = _make_project_integration(project_id=project_id, tool_name="adora_v3")
    integration = _make_integration()

    mock_pi_repo = MagicMock()
    mock_pi_repo.get_project_integrations_by_project_id.return_value = [adora_pi]
    mock_integration_repo = MagicMock()
    mock_integration_repo.get_integration_by_id.return_value = integration
    mock_project_repo = MagicMock()

    raw_menu = {
        "items": [],
        "modifier_weights": [{"modifier_weight_id": 1, "name": "Regular"}],
    }
    menu_assets = AdoraV3MenuAssets(
        english_menu_prompt="# Adora LLM Menu v9\n",
        menu_data={"items": {"pizza": [{"item_id": 1}]}, "version": 1},
    )

    with (
        patch(f"{PROJECTS_BASE}.project_service.get_project", return_value=project),
        patch(
            f"{PROJECTS_BASE}.db.ProjectIntegrationRepository",
            return_value=mock_pi_repo,
        ),
        patch(
            f"{PROJECTS_BASE}.db.IntegrationRepository",
            return_value=mock_integration_repo,
        ),
        patch(f"{PROJECTS_BASE}.ProjectRepository", return_value=mock_project_repo),
        patch(
            f"{PROJECTS_BASE}.get_client_secret",
            return_value=json.dumps({"client_id": "cid", "client_secret": "secret"}),
        ),
        patch(f"{PROJECTS_BASE}.get_bearer_token", return_value="bearer-token"),
        patch(f"{PROJECTS_BASE}.download_menu", return_value=raw_menu),
        patch(
            f"{PROJECTS_BASE}.build_menu_assets", return_value=menu_assets
        ) as mock_build_assets,
    ):
        result = update_knowledge(str(project_id), session=MagicMock())

    built_raw_menu = mock_build_assets.call_args[0][0]
    assert built_raw_menu["store_id"] == adora_pi.store_identifier

    mock_project_repo.update_project.assert_called_once_with(
        project_id, product_info=menu_assets.english_menu_prompt
    )
    mock_pi_repo.update_project_integration.assert_called_once()
    updated_config = mock_pi_repo.update_project_integration.call_args.kwargs["config"]
    assert updated_config["menu_data"] == menu_assets.menu_data
    mock_project_repo.update_project_config.assert_called_once()

    assert result["success"] is True
    assert result["product_info_updated"] is True
    assert result["menu_data_updated"] is True
    assert result["compiled_items"] == 1


@pytest.mark.asyncio
async def test_update_knowledge_rejects_non_object_menu_response():
    project_id = uuid.uuid4()
    account_id = uuid.uuid4()
    project = _make_project(id=project_id, account_id=account_id)
    adora_pi = _make_project_integration(project_id=project_id, tool_name="adora_v3")
    integration = _make_integration()

    mock_pi_repo = MagicMock()
    mock_pi_repo.get_project_integrations_by_project_id.return_value = [adora_pi]
    mock_integration_repo = MagicMock()
    mock_integration_repo.get_integration_by_id.return_value = integration

    with (
        patch(f"{PROJECTS_BASE}.project_service.get_project", return_value=project),
        patch(
            f"{PROJECTS_BASE}.db.ProjectIntegrationRepository",
            return_value=mock_pi_repo,
        ),
        patch(
            f"{PROJECTS_BASE}.db.IntegrationRepository",
            return_value=mock_integration_repo,
        ),
        patch(
            f"{PROJECTS_BASE}.get_client_secret",
            return_value=json.dumps({"client_id": "cid", "client_secret": "secret"}),
        ),
        patch(f"{PROJECTS_BASE}.get_bearer_token", return_value="bearer-token"),
        patch(f"{PROJECTS_BASE}.download_menu", return_value=[]),
    ):
        with pytest.raises(HTTPException, match="was not a JSON object") as exc_info:
            update_knowledge(str(project_id), session=MagicMock())
    assert exc_info.value.status_code == 400
