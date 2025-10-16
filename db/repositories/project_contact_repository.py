import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.project_contacts import ProjectContact
from utils.log import logger


class ProjectContactRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_project_contact_relation(
        self, project_id: uuid.UUID, contact_id: uuid.UUID
    ) -> ProjectContact:
        """
        Create a new project-contact relation asynchronously.
        Args:
            project_id (uuid.UUID): The project ID.
            contact_id (uuid.UUID): The contact ID.
        Returns:
            ProjectContact: The created project-contact relation.
        """
        project_contact = ProjectContact(
            project_id=project_id,
            contact_id=contact_id,
        )

        try:
            self.session.add(project_contact)
            await self.session.commit()
            await self.session.refresh(project_contact)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating project-contact relation: {e}")
            raise

        return project_contact

    async def delete_project_contact_relation(
        self, project_id: uuid.UUID, contact_id: uuid.UUID
    ) -> ProjectContact | None:
        """
        Delete a project-contact relation asynchronously.
        Args:
            project_id (uuid.UUID): The project ID.
            contact_id (uuid.UUID): The contact ID.
        Returns:
            ProjectContact: The deleted project-contact relation, or None if not found.
        """
        try:
            query = select(ProjectContact).filter(
                ProjectContact.project_id == project_id,
                ProjectContact.contact_id == contact_id,
            )
            result = await self.session.execute(query)
            project_contact = result.scalar_one_or_none()

            if project_contact is None:
                return None

            relation_snapshot = ProjectContact()
            for key, value in vars(project_contact).items():
                if not key.startswith("_"):
                    setattr(relation_snapshot, key, value)

            await self.session.delete(project_contact)
            await self.session.commit()
            return relation_snapshot
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting project-contact relation: {e}")
            raise
        except Exception as e:
            await self.session.rollback()
            logger.exception(
                f"Unexpected error while deleting project-contact relation {project_id}-{contact_id}: {e}"
            )
            raise

    async def list_contacts_by_project(self, project_id: uuid.UUID) -> List[uuid.UUID]:
        """
        List all contact IDs for a specific project asynchronously.
        Args:
            project_id (uuid.UUID): The project ID to filter by.
        Returns:
            List[uuid.UUID]: List of contact IDs for the project.
        """
        try:
            query = select(ProjectContact.contact_id).filter(
                ProjectContact.project_id == project_id
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving contacts for project {project_id}: {e}")
            raise
