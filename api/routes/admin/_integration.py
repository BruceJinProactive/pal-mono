"""Integration route handlers."""

import uuid

from fastapi import HTTPException, status
from pal_agents.menu_assets.toast.compiler import compile_toast_menu_v2
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
