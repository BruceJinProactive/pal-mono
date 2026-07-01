"""Integration route handlers."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from pal_agents.menu_assets.olo import OloMenuCompileError
from pal_agents.menu_assets.toast import (
    build_toast_lookup_prompt_context_markdown,
    compile_toast_menu_v2,
)
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

import db
import services.integration_service as integration_service
from api.schemas.admin.integration import (
    CreateProjectIntegrationRequest,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationType,
    ListIntegrationsResponse,
    ListProjectIntegrationsResponse,
    ProjectIntegrationResponse,
    UpdateIntegrationRequest,
    UpdateProjectIntegrationRequest,
)
from services.integration_service._utils import _get_integration_credentials
from services.knowledge_service.olo import (
    compile_olo_menu_data,
    fetch_and_compile_olo_menu_data,
)
from services.knowledge_service.toast._client import download_menu
from tools.toast_tool._apis import get_toast_access_token
from utils.log import logger

from ._builder import (
    build_integration,
    build_integration_summary,
    build_project_integration,
    build_project_integration_summary,
)
from ._utils import UserContext, not_found_error

TOAST_MENU_LAST_UPDATED_SOURCE_MANAGE_APP = "manage_app"
OLO_MENU_LAST_UPDATED_SOURCE_MANAGE_APP = "manage_app"
OLO_RAW_MENU_BUNDLE_CONFIG_KEY = "raw_menu_bundle"
OLO_AUTO_FETCH_MENU_DATA_CONFIG_KEY = "auto_fetch_menu_data"


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp_manual_toast_menu_update_metadata(
    config: dict | None,
    existing_config: dict | None = None,
) -> dict | None:
    """Stamp Toast menu metadata for Manage App saves that carry menu_data."""
    if config is None or config.get("menu_data") is None:
        return config

    updated_config = dict(config)
    existing_menu_data = (existing_config or {}).get("menu_data")
    menu_data_changed = (
        existing_config is None or config.get("menu_data") != existing_menu_data
    )
    if not menu_data_changed and existing_config:
        for metadata_key in ("menu_last_updated", "menu_last_updated_source"):
            if not updated_config.get(metadata_key) and existing_config.get(
                metadata_key
            ):
                updated_config[metadata_key] = existing_config[metadata_key]

    metadata_missing = not updated_config.get(
        "menu_last_updated"
    ) or not updated_config.get("menu_last_updated_source")

    if menu_data_changed or metadata_missing:
        updated_config["menu_last_updated"] = _utc_now_isoformat()
        updated_config["menu_last_updated_source"] = (
            TOAST_MENU_LAST_UPDATED_SOURCE_MANAGE_APP
        )

    return updated_config


def _build_toast_product_info(config: dict | None) -> str | None:
    """Build Menu / Product Info text from compiled Toast menu_data."""
    if not config:
        return None

    compiled_menu = config.get("menu_data")
    if not isinstance(compiled_menu, dict):
        return None

    return build_toast_lookup_prompt_context_markdown(compiled_menu)


def _compile_olo_config(
    config: dict,
    existing_config: dict | None = None,
) -> dict:
    raw_bundle = config.get(OLO_RAW_MENU_BUNDLE_CONFIG_KEY)
    if raw_bundle is None:
        return config
    if not isinstance(raw_bundle, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="olo_v1 config.raw_menu_bundle must be an object",
            headers={"Content-Type": "application/json"},
        )

    try:
        compiled_menu = compile_olo_menu_data(
            raw_bundle,
            selected_categories=config.get("selected_categories") or None,
            make_unique_categories=config.get("make_unique_categories") or None,
        )
    except OloMenuCompileError as exc:
        logger.error(
            "[OloIntegration] Failed to compile menu",
            extra={"error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to compile Olo menu: {exc}",
            headers={"Content-Type": "application/json"},
        ) from exc

    updated_config = {**(existing_config or {}), **config}
    updated_config.pop(OLO_RAW_MENU_BUNDLE_CONFIG_KEY, None)
    updated_config["menu_data"] = compiled_menu
    updated_config["menu_last_updated"] = _utc_now_isoformat()
    updated_config["menu_last_updated_source"] = OLO_MENU_LAST_UPDATED_SOURCE_MANAGE_APP
    return updated_config


def _get_raw_config_api_endpoint(raw_config: dict | None) -> str | None:
    api_endpoints = (raw_config or {}).get("api_endpoints")
    if not isinstance(api_endpoints, dict):
        return None

    endpoint = api_endpoints.get("general_api_endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None

    return endpoint.strip()


def _fetch_and_compile_olo_config(
    *,
    integration_id: uuid.UUID,
    account_id: uuid.UUID,
    store_identifier: str | None,
    config: dict | None,
    existing_config: dict | None = None,
) -> dict:
    """Fetch an Olo menu from account credentials and return compiled config."""
    from sqlalchemy import select

    from db.session import SyncSessionLocal
    from db.tables.integration import Integration as IntegrationModel

    config = {
        key: value
        for key, value in (config or {}).items()
        if key != OLO_AUTO_FETCH_MENU_DATA_CONFIG_KEY
    }
    restaurant_id = str(config.get("restaurant_id") or store_identifier or "").strip()
    if not restaurant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="olo_v1 config requires restaurant_id",
            headers={"Content-Type": "application/json"},
        )

    with SyncSessionLocal() as scoped_session:
        integration = scoped_session.execute(
            select(IntegrationModel).where(
                IntegrationModel.id == integration_id,
                IntegrationModel.account_id == account_id,
            )
        ).scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
            headers={"Content-Type": "application/json"},
        )

    try:
        credentials = _get_integration_credentials(integration.secret_key)
    except (KeyError, ValueError) as exc:
        logger.error(
            "[OloIntegration] Failed to read integration credentials",
            extra={"integration_id": str(integration_id), "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read integration credentials",
            headers={"Content-Type": "application/json"},
        ) from exc

    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is missing client_id or client_secret",
            headers={"Content-Type": "application/json"},
        )

    base_url = str(
        config.get("base_url")
        or _get_raw_config_api_endpoint(integration.raw_config)
        or ""
    ).strip()
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Olo general_api_endpoint is missing",
            headers={"Content-Type": "application/json"},
        )

    try:
        compiled_menu = fetch_and_compile_olo_menu_data(
            restaurant_id=restaurant_id,
            client_id=client_id,
            client_secret=client_secret,
            general_api_endpoint=base_url,
            selected_categories=config.get("selected_categories") or None,
            make_unique_categories=config.get("make_unique_categories") or None,
        )
    except (ValueError, OloMenuCompileError) as exc:
        logger.error(
            "[OloIntegration] Failed to fetch and compile menu",
            extra={"restaurant_id": restaurant_id, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch Olo menu: {exc}",
            headers={"Content-Type": "application/json"},
        ) from exc

    compiled_config = {**(existing_config or {}), **config}
    compiled_config.pop(OLO_RAW_MENU_BUNDLE_CONFIG_KEY, None)
    compiled_config["restaurant_id"] = restaurant_id
    compiled_config["menu_data"] = compiled_menu
    compiled_config["menu_last_updated"] = _utc_now_isoformat()
    compiled_config["menu_last_updated_source"] = (
        OLO_MENU_LAST_UPDATED_SOURCE_MANAGE_APP
    )

    logger.info(
        "[OloIntegration] Menu compiled for project integration",
        extra={"restaurant_id": restaurant_id},
    )
    return compiled_config


def _compile_toast_config(
    req: CreateProjectIntegrationRequest,
    account_id: uuid.UUID,
) -> CreateProjectIntegrationRequest:
    """Fetch and compile Toast menu, returning a new request with menu_data populated.

    Called when auto_fetch=True. Reads restaurant_guid, selected_menus,
    takeout_dining_option_guid, and delivery_dining_option_guid from config.
    selected_menus=None or [] compiles all menus.
    Creates its own DB session (safe to call from run_in_threadpool).
    Scopes integration lookup to account_id to prevent cross-tenant credential access.
    When auto_fetch=True, config.menu_data must be absent (enforced by validator).
    """
    from sqlalchemy import select

    from db.session import SyncSessionLocal
    from db.tables.integration import Integration as IntegrationModel

    config = req.config
    restaurant_guid: str = config["restaurant_guid"]
    selected_menus: list[str] | None = config.get("selected_menus") or None
    make_unique_menus = (
        selected_menus if config.get("make_unique", True) is not False else None
    )
    takeout_guid: str | None = config.get("takeout_dining_option_guid")
    delivery_guid: str | None = config.get("delivery_dining_option_guid")

    # Scope lookup to account_id to prevent cross-tenant credential access.
    with SyncSessionLocal() as session:
        integration = session.execute(
            select(IntegrationModel).where(
                IntegrationModel.id == req.integration_id,
                IntegrationModel.account_id == account_id,
            )
        ).scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
            headers={"Content-Type": "application/json"},
        )

    try:
        credentials = _get_integration_credentials(integration.secret_key)
    except (KeyError, ValueError) as exc:
        logger.error(
            "[ToastIntegration] Failed to read integration credentials",
            extra={"integration_id": str(req.integration_id), "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read integration credentials",
            headers={"Content-Type": "application/json"},
        )

    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Integration is missing client_id or client_secret",
            headers={"Content-Type": "application/json"},
        )

    bearer_token = get_toast_access_token(
        client_id=client_id,
        client_secret=client_secret,
    )
    if bearer_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Toast authentication failed — check integration credentials",
            headers={"Content-Type": "application/json"},
        )

    try:
        raw_menu = download_menu(bearer_token, restaurant_guid)
    except (RuntimeError, ValueError) as exc:
        logger.error(
            "[ToastIntegration] Failed to download menu",
            extra={"restaurant_guid": restaurant_guid, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to download Toast menu",
            headers={"Content-Type": "application/json"},
        )

    try:
        compiled_menu = compile_toast_menu_v2(
            raw_menu,
            selected_menus=selected_menus,  # None → compile all menus
            make_unique_menus=make_unique_menus,
            remove_unused_weights=True,
        )
    except Exception as exc:
        logger.error(
            "[ToastIntegration] Failed to compile menu",
            extra={"restaurant_guid": restaurant_guid, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to compile Toast menu",
            headers={"Content-Type": "application/json"},
        )

    compiled_config = {
        **config,  # preserve any other fields the caller sent
        "menu_data": compiled_menu,
        "takeout_dining_option_guid": takeout_guid,
        "delivery_dining_option_guid": delivery_guid,
        "submit_orders": config.get("submit_orders", False),
    }
    compiled_config = _stamp_manual_toast_menu_update_metadata(compiled_config) or {}

    logger.info(
        "[ToastIntegration] Menu compiled for project integration",
        extra={"restaurant_guid": restaurant_guid},
    )

    return req.model_copy(update={"config": compiled_config})


def list_integrations(
    account_name: str, context: UserContext, session: Session
) -> ListIntegrationsResponse:
    """Get all integrations for an account.
    Authorization is handled by require_account_permission in route decorator.
    """
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    integrations = integration_service.get_integrations_by_account_id(
        session, account.id
    )

    return ListIntegrationsResponse(
        integrations=[
            build_integration_summary(integration) for integration in integrations
        ]
    )


def get_integration(
    account_name: str, integration_id: uuid.UUID, context: UserContext, session: Session
) -> IntegrationResponse:
    """Get a specific integration.
    Authorization is handled by require_account_permission in route decorator.
    """
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    integration = integration_service.get_integration_by_id(
        session, account.id, integration_id
    )
    if not integration:
        raise not_found_error(f"Integration {integration_id} not found")

    return build_integration(integration)


def get_integration_by_project_and_type(
    account_name: str,
    project_id: uuid.UUID,
    integration_type: IntegrationType,
    context: UserContext,
    session: Session,
) -> IntegrationResponse:
    """Get an integration by project ID and type.
    Authorization is handled by require_account_permission in route decorator if exposed via API.
    """
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    integration = integration_service.get_integration_by_project_and_type(
        session, account.id, project_id, integration_type
    )
    if not integration:
        raise not_found_error(
            f"Integration of type {integration_type} not found for project {project_id}"
        )

    return build_integration(integration)


async def create_integration(
    account_name: str,
    integration: IntegrationRequest,
    context: UserContext,
    session: Session,
) -> IntegrationResponse:
    """Create a new integration.
    Authorization is handled by require_account_permission in route decorator.
    """
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    # Create integration with direct token storage
    created_integration = integration_service.create_integration(
        session=session,
        account=account,
        params=integration.to_integration_params(),
    )

    return build_integration(created_integration)


async def update_integration(
    account_name: str,
    integration_id: uuid.UUID,
    integration: UpdateIntegrationRequest,
    context: UserContext,
    session: Session,
) -> IntegrationResponse:
    """Update an integration.
    Authorization is handled by require_account_permission in route decorator.
    """
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    # Verify integration exists and belongs to account
    integration_service_integration = integration_service.get_integration_by_id(
        session, account.id, integration_id
    )
    if not integration_service_integration:
        raise not_found_error(f"Integration {integration_id} not found")

    # Update integration with direct token storage
    updated_integration = integration_service.update_integration(
        session=session,
        account=account,
        integration_id=integration_id,
        params=integration.to_integration_params(),
    )

    if not updated_integration:
        raise not_found_error(f"Integration {integration_id} not found")

    return build_integration(updated_integration)


async def delete_integration(
    account_name: str,
    integration_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> dict:
    """Delete an integration.
    Authorization is handled by require_account_permission in route decorator.
    """
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    # Verify integration exists and belongs to account
    integration_service_integration = integration_service.get_integration_by_id(
        session, account.id, integration_id
    )
    if not integration_service_integration:
        raise not_found_error(f"Integration {integration_id} not found")

    # Delete integration
    deleted_integration = integration_service.delete_integration(
        session, account.id, integration_id
    )

    if not deleted_integration:
        raise not_found_error(f"Integration {integration_id} not found")

    return {"message": "Integration deleted successfully"}


# Project Integration endpoints
def list_project_integrations(
    project_id: uuid.UUID, context: UserContext, session: Session
) -> ListProjectIntegrationsResponse:
    """Get all project integrations for a project.
    Authorization is handled by require_project_permission in route decorator.
    """
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")

    project_integrations = integration_service.get_project_integrations_by_project_id(
        session, project_id
    )

    return ListProjectIntegrationsResponse(
        project_integrations=[
            build_project_integration_summary(pi) for pi in project_integrations
        ]
    )


def get_project_integration(
    project_id: uuid.UUID,
    project_integration_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ProjectIntegrationResponse:
    """Get a project integration by ID.
    Authorization is handled by require_project_permission in route decorator.
    """
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")

    db_project_integration = integration_service.get_project_integration_by_id(
        session, project_integration_id
    )
    if not db_project_integration:
        raise not_found_error(f"Project integration {project_integration_id} not found")

    # Verify project integration belongs to this project
    if db_project_integration.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project integration does not belong to this project",
        )

    return build_project_integration(db_project_integration)


async def create_project_integration(
    project_id: uuid.UUID,
    project_integration: CreateProjectIntegrationRequest,
    context: UserContext,
    session: Session,
) -> ProjectIntegrationResponse:
    """Create a new project integration.

    For toast_v3 with auto_fetch=True: config.menu_data must be absent
    (validated at request boundary); menu is fetched and compiled automatically.
    When auto_fetch=False, config.menu_data is used as-is (manual path).
    """
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")

    # Toast auto-fetch: pass account_id for cross-tenant scoping;
    # _compile_toast_config creates its own session (thread-safe).
    if project_integration.tool_name == "toast_v3" and project_integration.auto_fetch:
        project_integration = await run_in_threadpool(
            _compile_toast_config, project_integration, project.account_id
        )
        try:
            product_info = _build_toast_product_info(project_integration.config)
        except Exception as exc:
            logger.error(
                "[ToastIntegration] Failed to build product info",
                extra={"project_id": str(project_id), "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to build Toast product info",
                headers={"Content-Type": "application/json"},
            ) from exc

        if product_info:
            updated_project = project_repository.update_project(
                project_id, product_info=product_info
            )
            if updated_project is None:
                raise not_found_error(f"Project {project_id} not found")
    elif project_integration.tool_name == "toast_v3":
        project_integration = project_integration.model_copy(
            update={
                "config": _stamp_manual_toast_menu_update_metadata(
                    project_integration.config
                )
            }
        )
    elif project_integration.tool_name == "olo_v1" and project_integration.auto_fetch:
        project_integration = await run_in_threadpool(
            lambda: project_integration.model_copy(
                update={
                    "config": _fetch_and_compile_olo_config(
                        integration_id=project_integration.integration_id,
                        account_id=project.account_id,
                        store_identifier=project_integration.store_identifier,
                        config=project_integration.config,
                    )
                }
            )
        )
    elif project_integration.tool_name == "olo_v1":
        project_integration = project_integration.model_copy(
            update={"config": _compile_olo_config(project_integration.config)}
        )

    created_project_integration = integration_service.create_project_integration(
        session=session,
        params=project_integration.to_project_integration_params(project_id),
    )

    return build_project_integration(created_project_integration)


async def update_project_integration(
    project_id: uuid.UUID,
    project_integration_id: uuid.UUID,
    project_integration: UpdateProjectIntegrationRequest,
    context: UserContext,
    session: Session,
) -> ProjectIntegrationResponse:
    """Update a project integration.
    Authorization is handled by require_project_permission in route decorator.
    """
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")

    # Verify project integration exists and belongs to project
    db_project_integration = integration_service.get_project_integration_by_id(
        session, project_integration_id
    )
    if not db_project_integration or db_project_integration.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project integration does not belong to this project",
        )

    # Get the integration_id from the existing project integration
    integration_id = db_project_integration.integration_id
    effective_tool_name = (
        project_integration.tool_name or db_project_integration.tool_name
    )
    if effective_tool_name == "toast_v3" and project_integration.config is not None:
        project_integration = project_integration.model_copy(
            update={
                "config": _stamp_manual_toast_menu_update_metadata(
                    project_integration.config,
                    db_project_integration.config,
                )
            }
        )
    should_auto_fetch_olo_menu = (
        effective_tool_name == "olo_v1"
        and project_integration.config is not None
        and project_integration.config.get(OLO_AUTO_FETCH_MENU_DATA_CONFIG_KEY) is True
    )
    if should_auto_fetch_olo_menu:
        store_identifier = (
            project_integration.store_identifier
            or db_project_integration.store_identifier
        )
        project_integration = await run_in_threadpool(
            lambda: project_integration.model_copy(
                update={
                    "store_identifier": store_identifier,
                    "config": _fetch_and_compile_olo_config(
                        integration_id=integration_id,
                        account_id=project.account_id,
                        store_identifier=store_identifier,
                        config=project_integration.config,
                        existing_config=db_project_integration.config,
                    ),
                }
            )
        )
    elif effective_tool_name == "olo_v1" and project_integration.config is not None:
        project_integration = project_integration.model_copy(
            update={
                "config": _compile_olo_config(
                    project_integration.config,
                    db_project_integration.config,
                )
            }
        )

    updated_project_integration = integration_service.update_project_integration(
        session=session,
        project_integration_id=project_integration_id,
        params=project_integration.to_project_integration_params(
            project_id, integration_id
        ),
    )

    if not updated_project_integration:
        raise not_found_error(f"Project integration {project_integration_id} not found")

    return build_project_integration(updated_project_integration)


async def delete_project_integration(
    project_id: uuid.UUID,
    project_integration_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> dict:
    """Delete a project integration.
    Authorization is handled by require_project_permission in route decorator.
    """
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")

    # Verify project integration exists and belongs to project
    db_project_integration = integration_service.get_project_integration_by_id(
        session, project_integration_id
    )
    if not db_project_integration or db_project_integration.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project integration does not belong to this project",
        )

    deleted_project_integration = integration_service.delete_project_integration(
        session, project_integration_id
    )

    if not deleted_project_integration:
        raise not_found_error(f"Project integration {project_integration_id} not found")

    return {"message": "Project integration deleted successfully"}
