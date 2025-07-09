import uuid
from dataclasses import asdict
from typing import List, Optional

from sqlalchemy.orm import Session

import db
from db.tables.integration import Integration, ProjectIntegration
from db.tables.types import IntegrationType
from services.integration_service.schema import (
    IntegrationParams,
    ProjectIntegrationParams,
)
from utils.log import logger


def get_integration_by_id(
    session: Session, account_id: uuid.UUID, integration_id: uuid.UUID
) -> Optional[Integration]:
    """Get an integration by its account ID and integration ID."""
    integration_repository = db.IntegrationRepository(session)
    return integration_repository.get_integration_by_id(account_id, integration_id)


def get_integrations_by_account_id(
    session: Session, account_id: uuid.UUID
) -> List[Integration]:
    """Get all integrations for an account."""
    integration_repository = db.IntegrationRepository(session)
    return integration_repository.get_integrations_by_account_id(account_id)


def get_integration_by_project_and_type(
    session: Session,
    account_id: uuid.UUID,
    project_id: uuid.UUID,
    integration_type: IntegrationType,
) -> Optional[Integration]:
    """Get an integration by project ID and type."""
    integration_repository = db.IntegrationRepository(session)
    return integration_repository.get_integration_by_project_and_type(
        account_id, project_id, integration_type
    )


def create_integration(
    session: Session,
    account_id: uuid.UUID,
    params: IntegrationParams,
) -> Integration:
    """Create a new integration."""
    integration_repository = db.IntegrationRepository(session)

    try:
        # Create integration with all data including tokens
        integration = integration_repository.create_integration(
            account_id=account_id, **asdict(params)
        )

        return integration
    except Exception as e:
        logger.error(f"Error creating integration: {e}")
        raise


def update_integration(
    session: Session,
    account_id: uuid.UUID,
    integration_id: uuid.UUID,
    params: IntegrationParams,
) -> Optional[Integration]:
    """Update an integration."""
    integration_repository = db.IntegrationRepository(session)

    try:
        # Convert params to dict and filter out None values
        update_data = {k: v for k, v in asdict(params).items() if v is not None}

        # Update integration
        integration = integration_repository.update_integration(
            account_id=account_id, integration_id=integration_id, **update_data
        )

        return integration
    except Exception as e:
        logger.error(f"Error updating integration: {e}")
        raise


def delete_integration(
    session: Session, account_id: uuid.UUID, integration_id: uuid.UUID
) -> Optional[Integration]:
    """Delete an integration."""
    integration_repository = db.IntegrationRepository(session)

    try:
        # Delete integration
        deleted_integration = integration_repository.delete_integration(
            account_id, integration_id
        )

        return deleted_integration
    except Exception as e:
        logger.error(f"Error deleting integration: {e}")
        raise


def get_project_integration_by_id(
    session: Session, project_integration_id: uuid.UUID
) -> Optional[ProjectIntegration]:
    """Get a project integration by its ID."""
    project_integration_repository = db.ProjectIntegrationRepository(session)
    return project_integration_repository.get_project_integration_by_id(
        project_integration_id
    )


def get_project_integrations_by_project_id(
    session: Session, project_id: uuid.UUID
) -> List[ProjectIntegration]:
    """Get all project integrations for a project."""
    project_integration_repository = db.ProjectIntegrationRepository(session)
    return project_integration_repository.get_project_integrations_by_project_id(
        project_id
    )


def create_project_integration(
    session: Session,
    params: ProjectIntegrationParams,
) -> ProjectIntegration:
    """Create a new project integration."""
    project_integration_repository = db.ProjectIntegrationRepository(session)

    try:
        return project_integration_repository.create_project_integration(
            project_id=uuid.UUID(params.project_id),
            integration_id=uuid.UUID(params.integration_id),
            store_identifier=params.store_identifier,
        )
    except Exception as e:
        logger.error(f"Error creating project integration: {e}")
        raise


def update_project_integration(
    session: Session,
    project_integration_id: uuid.UUID,
    params: ProjectIntegrationParams,
) -> Optional[ProjectIntegration]:
    """Update a project integration."""
    project_integration_repository = db.ProjectIntegrationRepository(session)

    try:
        return project_integration_repository.update_project_integration(
            project_integration_id=project_integration_id,
            store_identifier=params.store_identifier,
        )
    except Exception as e:
        logger.error(f"Error updating project integration: {e}")
        raise


def delete_project_integration(
    session: Session, project_integration_id: uuid.UUID
) -> Optional[ProjectIntegration]:
    """Delete a project integration."""
    project_integration_repository = db.ProjectIntegrationRepository(session)

    try:
        return project_integration_repository.delete_project_integration(
            project_integration_id
        )
    except Exception as e:
        logger.error(f"Error deleting project integration: {e}")
        raise
