import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Contact
from utils.log import logger


class ContactRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_contact(self, contact: Contact) -> Contact:
        """
        Create a new contact synchronously.
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
            self.session.commit()
            self.session.refresh(db_contact)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating contact: {e}")
            raise

        return db_contact

    def delete_contact(self, contact_id: uuid.UUID) -> Contact | None:
        """
        Delete a contact by ID synchronously.
        Args:
            contact_id (uuid.UUID): The ID of the contact to delete.
        Returns:
            Contact: The deleted contact, or None if not found.
        """
        try:
            query = select(Contact).filter(Contact.id == contact_id)
            result = self.session.execute(query)
            db_contact = result.scalar_one_or_none()

            if db_contact is None:
                return None

            contact_snapshot = Contact()
            for key, value in vars(db_contact).items():
                if not key.startswith("_"):
                    setattr(contact_snapshot, key, value)

            self.session.delete(db_contact)
            self.session.commit()
            return contact_snapshot
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting contact: {e}")
            raise
        except Exception as e:
            self.session.rollback()
            logger.exception(
                f"Unexpected error while deleting contact {contact_id}: {e}"
            )
            raise

    def batch_list_contacts(self, contact_ids: List[uuid.UUID]) -> List[Contact]:
        """
        List contacts by a batch of IDs synchronously.
        Args:
            contact_ids (List[uuid.UUID]): List of contact IDs to retrieve.
        Returns:
            List[Contact]: List of contacts matching the provided IDs.
        """
        try:
            query = select(Contact).filter(Contact.id.in_(contact_ids))
            result = self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving contacts by IDs: {e}")
            raise
