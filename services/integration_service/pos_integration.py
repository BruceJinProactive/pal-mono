import uuid
from typing import Optional

from sqlalchemy.orm import Session

from api.routes.admin import UserContext
from db.repositories.pos_integration_repository import POSIntegrationRepository
from db.tables.pos_integration import POSIntegration, POSProvider, POSState
from db.tables.projects import Project


def setup_project_pos_integration(
    session: Session,
    context: UserContext,
    project: Project,
    store_identifier: str,
    provider: POSProvider,
    state: POSState = POSState.ACTIVATE,
) -> POSIntegration:
    """
    Creates or updates the POS integration for the specified project.

    Args:
        session (Session): The database session to use.
        context (UserContext): The user context for the authenticated user.
        project (Project): The project to create the POS integration for.
        store_identifier (str): The store identifier for the POS system.
        provider (POSProvider): The POS provider to use.
        state (POSState): The state of the integration.

    Returns:
        POSIntegration: The created or updated POS integration.

    Raises:
        Exception: If there's an error creating or updating the POS integration.
    """
    repository = POSIntegrationRepository(session)

    # Check if project already has a POS integration
    existing_integration = repository.get_pos_integration_by_project_id(project.id)
    if existing_integration:
        # Update existing integration
        existing_integration.store_identifier = store_identifier
        existing_integration.provider = provider
        existing_integration.state = state
        session.commit()
        return existing_integration

    # Create new integration
    return repository.create_pos_integration(
        created_by=context.username,
        project_id=project.id,
        store_identifier=store_identifier,
        provider=provider,
        state=state,
    )


def get_project_pos_integration(
    session: Session, project_id: uuid.UUID
) -> Optional[POSIntegration]:
    """
    Get the POS integration for a project.

    Args:
        session (Session): The database session to use.
        project_id (uuid.UUID): The ID of the project to get the integration for.

    Returns:
        Optional[POSIntegration]: The POS integration if found, None otherwise.
    """
    repository = POSIntegrationRepository(session)
    return repository.get_pos_integration_by_project_id(project_id)
