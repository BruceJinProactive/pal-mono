import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.catering.catering import Contact as ContactSchema
from db.tables import Contact
from utils.log import logger


class ContactRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_schema(self, contact: Contact) -> ContactSchema:
        """
        Convert a Contact ORM object to a Pydantic model with all attributes loaded.
        This ensures no lazy loading issues when the object is used outside the session.
        """
        return ContactSchema(
            id=contact.id,
            name=contact.name,
            email=contact.email,
            phone_number=contact.phone_number,
            role=contact.role,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )

    async def create_contact(self, contact: Contact) -> ContactSchema:
        """
        Create a new contact asynchronously.
        Args:
            contact (Contact): The contact object to create.
        Returns:
            ContactSchema: The created contact as a Pydantic model.
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

        # Always return the created contact as Pydantic model
        return self._to_schema(db_contact)

    async def get_contact_by_id(self, contact_id: uuid.UUID) -> ContactSchema | None:
        """
        Get contact by ID asynchronously.

        Args:
            contact_id (uuid.UUID): The ID of the contact to retrieve.

        Returns:
            ContactSchema | None: The contact as Pydantic model if found, None otherwise.
        """
        try:
            query = select(Contact).filter(Contact.id == contact_id)
            result = await self.session.execute(query)
            db_contact = result.scalar_one_or_none()

            if db_contact:
                return self._to_schema(db_contact)

            return None
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

    async def batch_list_contacts(
        self, contact_ids: List[uuid.UUID]
    ) -> List[ContactSchema]:
        """
        List contacts by a batch of IDs asynchronously.
        Args:
            contact_ids (List[uuid.UUID]): List of contact IDs to retrieve.
        Returns:
            List[ContactSchema]: List of contact Pydantic models matching the provided IDs.
        """
        try:
            query = select(Contact).filter(Contact.id.in_(contact_ids))
            result = await self.session.execute(query)
            contacts = list(result.scalars().all())

            # Convert all contacts to Pydantic models to avoid session issues
            return [self._to_schema(contact) for contact in contacts]
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving contacts by IDs: {e}")
            raise

    async def update_contact(
        self,
        contact_id: uuid.UUID,
        name: str | None = None,
        email: str | None = None,
        phone_number: str | None = None,
        role: str | None = None,
    ) -> ContactSchema | None:
        """
        Update a contact by ID asynchronously.

        Args:
            contact_id (uuid.UUID): The ID of the contact to update.
            name: New name (optional).
            email: New email (optional).
            phone_number: New phone number (optional).
            role: New role (optional).

        Returns:
            ContactSchema | None: The updated contact as Pydantic model, or None if not found.
        """
        try:
            query = select(Contact).filter(Contact.id == contact_id)
            result = await self.session.execute(query)
            db_contact = result.scalar_one_or_none()

            if db_contact is None:
                return None

            # Update only provided fields
            if name is not None:
                db_contact.name = name
            if email is not None:
                db_contact.email = email
            if phone_number is not None:
                db_contact.phone_number = phone_number
            if role is not None:
                db_contact.role = role

            await self.session.commit()
            await self.session.refresh(db_contact)

            return self._to_schema(db_contact)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating contact {contact_id}: {e}")
            raise
