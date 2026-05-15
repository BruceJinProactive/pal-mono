from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.faq import FAQData
from db.tables.faqs import FAQ
from utils.log import logger

_MUTABLE_FIELDS: frozenset[str] = frozenset({"question", "answer", "project_id"})


def _to_data(row: FAQ) -> FAQData:
    """Convert an ORM FAQ to a FAQData."""
    return FAQData(
        id=row.id,
        account_id=row.account_id,
        question=row.question,
        answer=row.answer,
        created_at=row.created_at,
        project_id=row.project_id,
        updated_at=row.updated_at,
    )


class FAQRepository:
    """Async-only repository for FAQ records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, faq_id: uuid.UUID) -> FAQData | None:
        """Retrieve a FAQ by ID."""
        try:
            result = await self.session.execute(select(FAQ).filter(FAQ.id == faq_id))
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving FAQ by ID")
            raise

    async def get_by_account_id(
        self, account_id: uuid.UUID, project_id: uuid.UUID | None = None
    ) -> list[FAQData]:
        """Retrieve FAQs by account ID, optionally filtered by project."""
        try:
            query = select(FAQ).filter(FAQ.account_id == account_id)
            if project_id is not None:
                query = query.filter(FAQ.project_id == project_id)
            else:
                query = query.filter(FAQ.project_id.is_(None))
            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving FAQs by account ID")
            raise

    async def create(self, record: FAQData) -> FAQData:
        """Create a new FAQ."""
        try:
            row = FAQ(
                id=record.id,
                account_id=record.account_id,
                question=record.question,
                answer=record.answer,
                project_id=record.project_id,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating FAQ")
            raise

    async def update(self, faq_id: uuid.UUID, **kwargs: object) -> FAQData | None:
        """Update a FAQ by ID."""
        try:
            result = await self.session.execute(select(FAQ).filter(FAQ.id == faq_id))
            row = result.scalar_one_or_none()
            if not row:
                return None
            for key, value in kwargs.items():
                if key not in _MUTABLE_FIELDS:
                    raise ValueError(f"Cannot update field: {key}")
                setattr(row, key, value)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error updating FAQ")
            raise

    async def delete(self, faq_id: uuid.UUID) -> bool:
        """Delete a FAQ. Returns True if deleted."""
        try:
            result = await self.session.execute(select(FAQ).filter(FAQ.id == faq_id))
            row = result.scalar_one_or_none()
            if not row:
                return False
            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting FAQ")
            raise
