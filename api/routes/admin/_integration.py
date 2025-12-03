import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

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

from ._builder import (
    build_integration,
    build_integration_summary,
    build_project_integration,
    build_project_integration_summary,
)
from ._utils import UserContext, not_found_error


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
    Authorization is handled by require_project_permission in route decorator.
    """
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")

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
