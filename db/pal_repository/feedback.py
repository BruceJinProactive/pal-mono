from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.feedback import FeedbackData
from db.tables.feedback import Feedback
from utils.log import logger


def _to_data(row: Feedback) -> FeedbackData:
    """Convert an ORM Feedback to a FeedbackData."""
    return FeedbackData(
        id=row.id,
        message_id=row.message_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        author_identifier=row.author_identifier,
        author_name=row.author_name,
        reaction=row.reaction,
        tags=tuple(row.tags) if row.tags else (),
        note=row.note,
    )


class FeedbackRepository:
    """Async-only repository for Feedback records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, feedback_id: uuid.UUID) -> FeedbackData | None:
        """Retrieve a feedback by ID."""
        try:
            result = await self.session.execute(
                select(Feedback).filter(Feedback.id == feedback_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving feedback by ID")
            raise

    async def get_by_message_ids(
        self, message_ids: list[uuid.UUID]
    ) -> list[FeedbackData]:
        """Retrieve feedback for a list of message IDs."""
        if not message_ids:
            return []
        try:
            result = await self.session.execute(
                select(Feedback).filter(Feedback.message_id.in_(message_ids))
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving feedback by message IDs")
            raise

    async def create(self, record: FeedbackData) -> FeedbackData:
        """Create a new feedback entry."""
        try:
            row = Feedback(
                message_id=record.message_id,
                author_identifier=record.author_identifier,
                author_name=record.author_name,
                reaction=record.reaction,
                tags=list(record.tags) if record.tags else [],
                note=record.note,
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating feedback")
            raise

    async def delete(self, feedback_id: uuid.UUID) -> FeedbackData | None:
        """Delete a feedback. Returns deleted data or None if not found."""
        try:
            result = await self.session.execute(
                select(Feedback).filter(Feedback.id == feedback_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting feedback")
            raise
