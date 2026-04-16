from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.contact import ContactData
from db.pal_repository.data_classes.routine_execution import UNSET, _Unset
from db.tables.contacts import Contact
from utils.log import logger


def _to_data(row: Contact) -> ContactData:
    """Convert an ORM Contact to a ContactData."""
    return ContactData(
        id=row.id,
        name=row.name,
        email=row.email,
        phone_number=row.phone_number,
        role=row.role,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ContactRepository:
    """Async-only repository for Contact records.

    All methods return ``ContactData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, contact_id: uuid.UUID) -> ContactData | None:
        """Retrieve a single contact by its primary key."""
        try:
            result = await self.session.execute(
                select(Contact).filter(Contact.id == contact_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving contact by ID")
            raise

    async def batch_get_by_ids(self, contact_ids: list[uuid.UUID]) -> list[ContactData]:
        """Retrieve contacts by a batch of IDs."""
        if not contact_ids:
            return []
        try:
            result = await self.session.execute(
                select(Contact).filter(Contact.id.in_(contact_ids))
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving contacts by IDs")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(
        self,
        name: str,
        phone_number: str,
        role: str,
        email: str | None = None,
    ) -> ContactData:
        """Create a new contact and return the created record.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = Contact(
                name=name,
                phone_number=phone_number,
                role=role,
                email=email,
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating contact: {e}")
            raise

    async def update(
        self,
        contact_id: uuid.UUID,
        name: str | _Unset = UNSET,
        email: str | None | _Unset = UNSET,
        phone_number: str | _Unset = UNSET,
        role: str | _Unset = UNSET,
    ) -> ContactData | None:
        """Update a contact by ID. Only provided fields are updated.

        Pass ``None`` explicitly to clear a nullable field (e.g. ``email``).
        Omit a parameter to leave it unchanged.

        Returns the updated record, or None if not found.
        """
        try:
            result = await self.session.execute(
                select(Contact).filter(Contact.id == contact_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None

            if not isinstance(name, _Unset):
                row.name = name
            if not isinstance(email, _Unset):
                row.email = email
            if not isinstance(phone_number, _Unset):
                row.phone_number = phone_number
            if not isinstance(role, _Unset):
                row.role = role

            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating contact {contact_id}: {e}")
            raise

    async def delete(self, contact_id: uuid.UUID) -> ContactData | None:
        """Delete a contact by its ID.

        Returns the deleted record, or None if no match was found.
        """
        try:
            result = await self.session.execute(
                select(Contact).filter(Contact.id == contact_id)
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
            logger.error(f"Error deleting contact: {e}")
            raise
