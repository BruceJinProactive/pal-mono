import uuid
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables.integration import Integration, ProjectIntegration
from db.tables.types import AuthType, IntegrationProvider, IntegrationType
from utils.log import logger


class IntegrationRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_integration_by_id(
        self, account_id: uuid.UUID, integration_id: uuid.UUID
    ) -> Integration | None:
        """Retrieve an integration by its account ID and integration ID."""
        try:
            return (
                self.session.query(Integration)
                .filter(Integration.account_id == account_id)
                .filter(Integration.id == integration_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"Error retrieving integration by account ID and integration ID: {e}"
            )
            return None

    def get_integrations_by_account_id(
        self, account_id: uuid.UUID
    ) -> List[Integration]:
        """Retrieve all integrations for an account."""
        try:
            return (
                self.session.query(Integration)
                .filter(Integration.account_id == account_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving integrations by account ID: {e}")
            return []

    def get_integrations_by_provider_and_type(
        self,
        account_id: uuid.UUID,
        provider: IntegrationProvider,
        integration_type: IntegrationType,
    ) -> List[Integration]:
        """Retrieve integrations by provider and type for an account."""
        try:
            return (
                self.session.query(Integration)
                .filter(Integration.account_id == account_id)
                .filter(Integration.provider == provider)
                .filter(Integration.integration_type == integration_type)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving integrations by provider and type: {e}")
            return []

    def get_integration_by_project_and_type(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID,
        integration_type: IntegrationType,
    ) -> Integration | None:
        """Retrieve an integration by project ID and type."""
        try:
            return (
                self.session.query(Integration)
                .join(
                    ProjectIntegration,
                    Integration.id == ProjectIntegration.integration_id,
                )
                .filter(Integration.account_id == account_id)
                .filter(ProjectIntegration.project_id == project_id)
                .filter(Integration.integration_type == integration_type)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving integration by project and type: {e}")
            return None

    def create_integration(
        self,
        account_id: uuid.UUID,
        provider: IntegrationProvider,
        integration_type: IntegrationType,
        auth_type: AuthType,
        **kwargs,
    ) -> Integration:
        """Create a new integration."""
        try:
            db_integration = Integration(
                id=uuid.uuid4(),
                account_id=account_id,
                provider=provider,
                integration_type=integration_type,
                auth_type=auth_type,
                **kwargs,
            )

            self.session.add(db_integration)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_integration)
            return db_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating integration: {e}")
            raise

    def update_integration(
        self, account_id: uuid.UUID, integration_id: uuid.UUID, **kwargs
    ) -> Integration | None:
        """Update integration details."""
        try:
            db_integration = (
                self.session.query(Integration)
                .filter(Integration.account_id == account_id)
                .filter(Integration.id == integration_id)
                .first()
            )
            if not db_integration:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(db_integration, key):
                    setattr(db_integration, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_integration)
            return db_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating integration: {e}")
            raise

    def delete_integration(
        self, account_id: uuid.UUID, integration_id: uuid.UUID
    ) -> Optional[Integration]:
        """Delete an integration by its account ID and integration ID."""
        try:
            db_integration = (
                self.session.query(Integration)
                .filter(Integration.account_id == account_id)
                .filter(Integration.id == integration_id)
                .first()
            )
            if db_integration:
                self.session.delete(db_integration)

                if self.auto_commit:
                    self.session.commit()
                else:
                    self.session.flush()
            return db_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting integration: {e}")
            raise
