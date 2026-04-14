from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.signal_feed import SignalFeedData
from db.tables.signal_feeds import SignalFeed
from db.tables.types import CaptureMode, FeedType, SignalFeedStatus
from utils.log import logger


def _to_data(row: SignalFeed) -> SignalFeedData:
    """Convert an ORM SignalFeed to a SignalFeedData."""
    if row.feed_type is None or row.capture_mode is None or row.status is None:
        raise ValueError("SignalFeed row is missing required enum values")

    return SignalFeedData(
        id=row.id,
        source_id=row.source_id,
        feed_type=row.feed_type.value,
        capture_mode=row.capture_mode.value,
        status=row.status.value,
        status_message=row.status_message,
        last_capture_at=row.last_capture_at,
        last_capture_url=row.last_capture_url,
        capture_count=row.capture_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SignalFeedRepository:
    """Async-only repository for SignalFeed records.

    All methods return ``SignalFeedData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, feed_id: uuid.UUID) -> SignalFeedData | None:
        """Retrieve a single signal feed by its primary key."""
        try:
            result = await self.session.execute(
                select(SignalFeed).filter(SignalFeed.id == feed_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving signal feed by ID")
            raise

    async def list_by_source_id(self, source_id: uuid.UUID) -> list[SignalFeedData]:
        """List all feeds for a given source."""
        try:
            result = await self.session.execute(
                select(SignalFeed)
                .filter(SignalFeed.source_id == source_id)
                .order_by(SignalFeed.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing signal feeds by source ID")
            raise

    async def list_by_status(self, status: str) -> list[SignalFeedData]:
        """List all feeds with a given status."""
        try:
            result = await self.session.execute(
                select(SignalFeed)
                .filter(SignalFeed.status == SignalFeedStatus(status))
                .order_by(SignalFeed.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing signal feeds by status")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: SignalFeedData) -> None:
        """Create a new signal feed.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = SignalFeed(
                id=record.id,
                source_id=record.source_id,
                feed_type=FeedType(record.feed_type),
                capture_mode=CaptureMode(record.capture_mode),
                status=SignalFeedStatus(record.status),
                status_message=record.status_message,
                last_capture_at=record.last_capture_at,
                last_capture_url=record.last_capture_url,
                capture_count=record.capture_count,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating signal feed: {e}")
            raise

    async def delete(self, feed_id: uuid.UUID) -> SignalFeedData | None:
        """Delete a signal feed by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(SignalFeed).filter(SignalFeed.id == feed_id)
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
            logger.error(f"Error deleting signal feed: {e}")
            raise
