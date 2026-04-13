from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.project_integration import ProjectIntegrationData
from db.tables.integration import ProjectIntegration
from utils.log import logger


def _to_data(row: ProjectIntegration) -> ProjectIntegrationData:
    """Convert an ORM ProjectIntegration to a ProjectIntegrationData."""
    return ProjectIntegrationData(
        id=row.id,
        project_id=row.project_id,
        integration_id=row.integration_id,
        store_identifier=row.store_identifier,
        tool_name=row.tool_name,
        config=dict(row.config) if row.config else {},
        created_at=row.created_at,
    )


class ProjectIntegrationRepository:
    """Async-only repository for ProjectIntegration records.

    All methods return ``ProjectIntegrationData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, project_integration_id: uuid.UUID
    ) -> ProjectIntegrationData | None:
        """Retrieve a single project integration by its primary key."""
        try:
            result = await self.session.execute(
                select(ProjectIntegration).filter(
                    ProjectIntegration.id == project_integration_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving project integration by ID: {e}")
            raise

    async def list_by_project_id(
        self, project_id: uuid.UUID
    ) -> list[ProjectIntegrationData]:
        """List all project integrations for a given project."""
        try:
            result = await self.session.execute(
                select(ProjectIntegration).filter(
                    ProjectIntegration.project_id == project_id
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception as e:
            logger.error(f"Error listing project integrations by project ID: {e}")
            raise

    async def list_by_integration_id(
        self, integration_id: uuid.UUID
    ) -> list[ProjectIntegrationData]:
        """List all project integrations linked to a given integration."""
        try:
            result = await self.session.execute(
                select(ProjectIntegration).filter(
                    ProjectIntegration.integration_id == integration_id
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception as e:
            logger.error(f"Error listing project integrations by integration ID: {e}")
            raise

    async def get_by_project_and_integration(
        self, project_id: uuid.UUID, integration_id: uuid.UUID
    ) -> ProjectIntegrationData | None:
        """Retrieve a single project integration by project and integration IDs."""
        try:
            result = await self.session.execute(
                select(ProjectIntegration)
                .filter(ProjectIntegration.project_id == project_id)
                .filter(ProjectIntegration.integration_id == integration_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception as e:
            logger.error(
                f"Error retrieving project integration by project and integration IDs: {e}"
            )
            raise

    async def create(self, record: ProjectIntegrationData) -> None:
        """Create a new project integration.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = ProjectIntegration(
                id=record.id,
                project_id=record.project_id,
                integration_id=record.integration_id,
                store_identifier=record.store_identifier,
                tool_name=record.tool_name,
                config=record.config or {},
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating project integration: {e}")
            raise

    async def update(
        self,
        project_integration_id: uuid.UUID,
        record: ProjectIntegrationData,
    ) -> None:
        """Update an existing project integration.

        Fields from *record* that are non-None overwrite the existing values.
        """
        try:
            result = await self.session.execute(
                select(ProjectIntegration).filter(
                    ProjectIntegration.id == project_integration_id
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            if record.store_identifier is not None:
                row.store_identifier = record.store_identifier
            if record.tool_name is not None:
                row.tool_name = record.tool_name
            if record.config is not None:
                row.config = record.config

            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating project integration: {e}")
            raise

    async def delete(
        self, project_integration_id: uuid.UUID
    ) -> ProjectIntegrationData | None:
        """Delete a project integration by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(ProjectIntegration).filter(
                    ProjectIntegration.id == project_integration_id
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting project integration: {e}")
            raise
