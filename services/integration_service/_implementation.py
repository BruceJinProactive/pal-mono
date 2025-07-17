import uuid
from dataclasses import asdict
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from db import Account
from db.tables.integration import Integration, ProjectIntegration
from db.tables.types import IntegrationType
from services.integration_service._utils import (
    build_integration_detail,
    update_integration_credentials,
)
from services.integration_service.schema import (
    CreateIntegrationParams,
    IntegrationDetail,
    ProjectIntegrationParams,
    UpdateIntegrationParams,
)
from utils.log import logger
from utils.secret import remove_client_secret

# ------------ Integration ------------


def create_integration(
    session: Session,
    account: Account,
    params: CreateIntegrationParams,
) -> IntegrationDetail:
    """Create a new integration with secrets stored in secret manager.

    All required fields must be provided for creation.
    """
    integration_repository = db.IntegrationRepository(session, auto_commit=False)

    try:
        # Create integration with all required fields
        integration = integration_repository.create_integration(
            account_id=account.id,
            provider=params.provider,
            integration_type=params.integration_type,
            auth_type=params.auth_type,
        )

        # Write credentials to secret manager
        secret_key = update_integration_credentials(
            account, params.credentials, integration
        )

        # Update integration with secret key value and get the updated object
        updated_integration = integration_repository.update_integration(
            account_id=account.id,
            integration_id=integration.id,
            secret_key=secret_key,
            business_id=params.business_id,
            raw_config=params.raw_config,
        )

        if not updated_integration:
            raise ValueError("Failed to update integration after creation")

        session.commit()
        return build_integration_detail(updated_integration)
    except Exception as e:
        session.rollback()
        # TODO: Clean up orphaned secret from secret manager if transaction fails
        # This would require storing the secret_key and calling remove_client_secret(secret_key)
        logger.error(f"Error creating integration: {e}")
        raise


def update_integration(
    session: Session,
    account: Account,
    integration_id: uuid.UUID,
    params: UpdateIntegrationParams,
) -> Optional[IntegrationDetail]:
    """Update an integration with partial updates.

    All fields are optional. If credentials are provided, they will be updated
    in the secret manager using the existing secret_key.
    """
    integration_repository = db.IntegrationRepository(session, auto_commit=False)

    try:
        # Convert params to dict and filter out None values
        update_data = {
            k: v
            for k, v in asdict(params).items()
            if v is not None and k != "credentials"
        }

        # Update integration with non-credential fields
        integration = integration_repository.update_integration(
            account_id=account.id, integration_id=integration_id, **update_data
        )

        if not integration:
            return None

        # Handle credentials separately if provided
        if params.credentials:
            # Update credentials in secret manager using existing secret_key
            secret_key = update_integration_credentials(
                account, params.credentials, integration
            )
            # Only update secret_key if it changed (e.g., if it was initially None)
            if secret_key != integration.secret_key:
                integration = integration_repository.update_integration(
                    account_id=account.id,
                    integration_id=integration_id,
                    secret_key=secret_key,
                )
        session.commit()
        return build_integration_detail(integration)
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating integration: {e}")
        raise


def get_integration_by_id(
    session: Session, account_id: uuid.UUID, integration_id: uuid.UUID
) -> Optional[IntegrationDetail]:
    """Get an integration by its account ID and integration ID."""
    integration_repository = db.IntegrationRepository(session)
    integration = integration_repository.get_integration_by_id(
        account_id, integration_id
    )

    if integration:
        return build_integration_detail(integration)

    return integration


def get_integrations_by_account_id(
    session: Session, account_id: uuid.UUID
) -> List[IntegrationDetail]:
    """Get all integrations for an account."""
    integration_repository = db.IntegrationRepository(session)
    integrations = integration_repository.get_integrations_by_account_id(account_id)
    return [build_integration_detail(integration) for integration in integrations]


def get_integration_by_project_and_type(
    session: Session,
    account_id: uuid.UUID,
    project_id: uuid.UUID,
    integration_type: IntegrationType,
) -> Optional[IntegrationDetail]:
    """Get an integration by project ID and type."""
    integration_repository = db.IntegrationRepository(session)
    integration = integration_repository.get_integration_by_project_and_type(
        account_id, project_id, integration_type
    )
    if integration:
        return build_integration_detail(integration)

    return integration


async def async_get_integration_by_project_and_type(
    session: AsyncSession,
    account_id: uuid.UUID,
    project_id: uuid.UUID,
    integration_type: IntegrationType,
) -> Optional[IntegrationDetail]:
    """Get an integration by project ID and type."""
    integration_repository = db.IntegrationAsyncRepository(session)
    integration = await integration_repository.get_integration_by_project_and_type(
        account_id, project_id, integration_type
    )
    if integration:
        return build_integration_detail(integration)

    return integration


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
        # Remove secret key from secret manager
        if deleted_integration and deleted_integration.secret_key:
            remove_client_secret(deleted_integration.secret_key)

        return deleted_integration
    except Exception as e:
        logger.error(f"Error deleting integration: {e}")
        raise


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


# ------------ Project Integration ------------


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
