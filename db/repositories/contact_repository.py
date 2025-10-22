import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import Contact
from utils.log import logger


class ContactRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_contact(self, contact: Contact) -> Contact:
        """
        Create a new contact asynchronously.
        Args:
            contact (Contact): The contact object to create.
        Returns:
            Contact: The created contact with generated ID and timestamps.
        """
        db_contact = Contact()
        for key, value in vars(contact).items():
            if hasattr(Contact, key) and key not in {
                "id",
                "created_at",
                "updated_at",
            }:
                setattr(db_contact, key, value)

        try:
            self.session.add(db_contact)
            await self.session.commit()
            await self.session.refresh(db_contact)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating contact: {e}")
            raise

        return db_contact

    async def get_contact_by_id(self, contact_id: uuid.UUID) -> Contact | None:
        """
        Get contact by ID asynchronously.

        Args:
            contact_id (uuid.UUID): The ID of the contact to retrieve.

        Returns:
            Contact | None: The contact if found, None otherwise.
        """
        try:
            query = select(Contact).filter(Contact.id == contact_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving contact by ID {contact_id}: {e}")
            raise

    async def delete_contact(self, contact_id: uuid.UUID) -> Contact | None:
        """
        Delete a contact by ID asynchronously.
        Args:
            contact_id (uuid.UUID): The ID of the contact to delete.
        Returns:
            Contact: The deleted contact, or None if not found.
        """
        try:
            query = select(Contact).filter(Contact.id == contact_id)
            result = await self.session.execute(query)
            db_contact = result.scalar_one_or_none()

            if db_contact is None:
                return None

            contact_snapshot = Contact()
            for key, value in vars(db_contact).items():
                if not key.startswith("_"):
                    setattr(contact_snapshot, key, value)

            await self.session.delete(db_contact)
            await self.session.commit()
            return contact_snapshot
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting contact: {e}")
            raise
        except Exception as e:
            await self.session.rollback()
            logger.exception(
                f"Unexpected error while deleting contact {contact_id}: {e}"
            )
            raise

    async def batch_list_contacts(self, contact_ids: List[uuid.UUID]) -> List[Contact]:
        """
        List contacts by a batch of IDs asynchronously.
        Args:
            contact_ids (List[uuid.UUID]): List of contact IDs to retrieve.
        Returns:
            List[Contact]: List of contacts matching the provided IDs.
        """
        try:
            query = select(Contact).filter(Contact.id.in_(contact_ids))
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving contacts by IDs: {e}")
            raise
