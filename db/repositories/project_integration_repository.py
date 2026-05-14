import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables.integration import Integration, ProjectIntegration
from db.tables.types import IntegrationProvider
from utils.log import logger


class ProjectIntegrationRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project_integrations_by_store_identifier_and_provider(
        self, store_identifier: str, provider: IntegrationProvider
    ) -> List[ProjectIntegration]:
        """Retrieve project integrations by store identifier and integration provider."""
        try:
            result = await self.session.execute(
                select(ProjectIntegration)
                .join(Integration, ProjectIntegration.integration_id == Integration.id)
                .filter(ProjectIntegration.store_identifier == store_identifier)
                .filter(Integration.provider == provider)
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(
                "Error retrieving project integrations by store identifier and provider: %s",
                e,
            )
            return []


class ProjectIntegrationRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_project_integration_by_id(
        self, project_integration_id: uuid.UUID
    ) -> ProjectIntegration | None:
        """Retrieve a project integration by its ID."""
        try:
            return (
                self.session.query(ProjectIntegration)
                .filter(ProjectIntegration.id == project_integration_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving project integration by ID: {e}")
            return None

    def get_project_integrations_by_project_id(
        self, project_id: uuid.UUID
    ) -> List[ProjectIntegration]:
        """Retrieve all project integrations for a project."""
        try:
            return (
                self.session.query(ProjectIntegration)
                .filter(ProjectIntegration.project_id == project_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving project integrations by project ID: {e}")
            return []

    def get_project_integrations_by_integration_id(
        self, integration_id: uuid.UUID
    ) -> List[ProjectIntegration]:
        """Retrieve all project integrations for an integration."""
        try:
            return (
                self.session.query(ProjectIntegration)
                .filter(ProjectIntegration.integration_id == integration_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"Error retrieving project integrations by integration ID: {e}"
            )
            return []

    def get_project_integrations_by_store_identifier_and_provider(
        self, store_identifier: str, provider: IntegrationProvider
    ) -> List[ProjectIntegration]:
        """Retrieve project integrations by store identifier and integration provider."""
        try:
            return (
                self.session.query(ProjectIntegration)
                .join(Integration, ProjectIntegration.integration_id == Integration.id)
                .filter(ProjectIntegration.store_identifier == store_identifier)
                .filter(Integration.provider == provider)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                "Error retrieving project integrations by store identifier and provider: %s",
                e,
            )
            return []

    def get_project_integration_by_project_and_integration(
        self, project_id: uuid.UUID, integration_id: uuid.UUID
    ) -> ProjectIntegration | None:
        """Retrieve a specific project integration by project and integration IDs."""
        try:
            return (
                self.session.query(ProjectIntegration)
                .filter(ProjectIntegration.project_id == project_id)
                .filter(ProjectIntegration.integration_id == integration_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"Error retrieving project integration by project and integration IDs: {e}"
            )
            return None

    def create_project_integration(
        self,
        project_id: uuid.UUID,
        integration_id: uuid.UUID,
        store_identifier: str,
        **kwargs,
    ) -> ProjectIntegration:
        """Create a new project integration."""
        try:
            db_project_integration = ProjectIntegration(
                id=uuid.uuid4(),
                project_id=project_id,
                integration_id=integration_id,
                store_identifier=store_identifier,
                **kwargs,
            )

            self.session.add(db_project_integration)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_project_integration)
            return db_project_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating project integration: {e}")
            raise

    def update_project_integration(
        self, project_integration_id: uuid.UUID, **kwargs
    ) -> ProjectIntegration | None:
        """Update project integration details."""
        try:
            db_project_integration = (
                self.session.query(ProjectIntegration)
                .filter(ProjectIntegration.id == project_integration_id)
                .first()
            )
            if not db_project_integration:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(db_project_integration, key):
                    setattr(db_project_integration, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_project_integration)
            return db_project_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating project integration: {e}")
            raise

    def delete_project_integration(
        self, project_integration_id: uuid.UUID
    ) -> Optional[ProjectIntegration]:
        """Delete a project integration by its ID."""
        try:
            db_project_integration = (
                self.session.query(ProjectIntegration)
                .filter(ProjectIntegration.id == project_integration_id)
                .first()
            )
            if db_project_integration:
                self.session.delete(db_project_integration)

                if self.auto_commit:
                    self.session.commit()
                else:
                    self.session.flush()
            return db_project_integration
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting project integration: {e}")
            raise
