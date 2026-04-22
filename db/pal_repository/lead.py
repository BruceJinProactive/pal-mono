from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.lead import LeadData
from db.tables.lead import Lead
from utils.log import logger

_MUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "business_name",
        "business_address",
        "logo_uri",
        "segment",
        "tier",
        "pos",
        "channels",
        "account_id",
        "owner",
        "hubspot_record_id",
        "status",
        "contract_signed",
        "notes",
    }
)


def _to_data(row: Lead) -> LeadData:
    """Convert an ORM Lead to a LeadData."""
    return LeadData(
        id=row.id,
        status=row.status.value,
        contract_signed=row.contract_signed,
        deleted=row.deleted,
        created_at=row.created_at,
        business_name=row.business_name,
        business_address=row.business_address,
        logo_uri=row.logo_uri,
        segment=row.segment.value if row.segment else None,
        tier=row.tier.value if row.tier else None,
        pos=row.pos,
        channels=tuple(row.channels) if row.channels else (),
        account_id=row.account_id,
        owner=row.owner,
        hubspot_record_id=row.hubspot_record_id,
        notes=row.notes,
        updated_at=row.updated_at,
    )


def _validate_mutable_fields(kwargs: dict[str, object], action: str) -> None:
    """Raise ValueError for any key not in _MUTABLE_FIELDS."""
    for key in kwargs:
        if key not in _MUTABLE_FIELDS:
            raise ValueError(f"Cannot {action} field: {key}")


class LeadRepository:
    """Async-only repository for Lead records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, lead_id: uuid.UUID) -> LeadData | None:
        """Retrieve a lead by ID (excludes deleted)."""
        try:
            result = await self.session.execute(
                select(Lead).filter(Lead.id == lead_id, Lead.deleted.is_not(True))
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving lead by ID")
            raise

    async def create(self, **kwargs: object) -> LeadData:
        """Create a new lead."""
        _validate_mutable_fields(kwargs, "set")
        try:
            row = Lead(id=uuid.uuid4())
            for key, value in kwargs.items():
                setattr(row, key, value)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating lead")
            raise

    async def update(self, lead_id: uuid.UUID, **kwargs: object) -> LeadData | None:
        """Update a lead by ID."""
        _validate_mutable_fields(kwargs, "update")
        try:
            result = await self.session.execute(
                select(Lead).filter(Lead.id == lead_id, Lead.deleted.is_not(True))
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            for key, value in kwargs.items():
                setattr(row, key, value)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error updating lead")
            raise

    async def delete(self, lead_id: uuid.UUID) -> None:
        """Soft-delete a lead."""
        try:
            result = await self.session.execute(
                select(Lead).filter(Lead.id == lead_id, Lead.deleted.is_not(True))
            )
            row = result.scalar_one_or_none()
            if row:
                row.deleted = True
                await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting lead")
            raise
