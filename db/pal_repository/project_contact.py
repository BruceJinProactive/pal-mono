from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.project_contact import ProjectContactData
from db.tables.project_contacts import ProjectContact
from utils.log import logger


def _to_data(row: ProjectContact) -> ProjectContactData:
    """Convert an ORM ProjectContact to a ProjectContactData."""
    return ProjectContactData(
        id=row.id,
        project_id=row.project_id,
        contact_id=row.contact_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProjectContactRepository:
    """Async-only repository for ProjectContact records.

    All methods return ``ProjectContactData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, project_contact_id: uuid.UUID
    ) -> ProjectContactData | None:
        """Retrieve a project contact by its ID."""
        try:
            result = await self.session.execute(
                select(ProjectContact).filter(ProjectContact.id == project_contact_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project contact by ID: {e}")
            raise

    async def get_by_project_id(
        self, project_id: uuid.UUID
    ) -> list[ProjectContactData]:
        """Retrieve all project contacts for a given project."""
        try:
            result = await self.session.execute(
                select(ProjectContact).filter(ProjectContact.project_id == project_id)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project contacts by project ID: {e}")
            raise

    async def get_by_contact_id(
        self, contact_id: uuid.UUID
    ) -> list[ProjectContactData]:
        """Retrieve all project contacts linked to a given contact."""
        try:
            result = await self.session.execute(
                select(ProjectContact).filter(ProjectContact.contact_id == contact_id)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project contacts by contact ID: {e}")
            raise

    async def get_by_project_and_contact(
        self, project_id: uuid.UUID, contact_id: uuid.UUID
    ) -> ProjectContactData | None:
        """Retrieve a project contact by both project and contact IDs."""
        try:
            result = await self.session.execute(
                select(ProjectContact)
                .filter(ProjectContact.project_id == project_id)
                .filter(ProjectContact.contact_id == contact_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving project contact by project and contact IDs: {e}"
            )
            raise

    async def create(self, record: ProjectContactData) -> None:
        """Create a new project contact.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = ProjectContact(
                id=record.id,
                project_id=record.project_id,
                contact_id=record.contact_id,
            )
            self.session.add(row)
            await self.session.commit()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating project contact: {e}")
            raise

    async def delete(self, project_contact_id: uuid.UUID) -> ProjectContactData | None:
        """Delete a project contact by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(ProjectContact).filter(ProjectContact.id == project_contact_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting project contact: {e}")
            raise
