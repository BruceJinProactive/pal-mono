"""Signal Feed Repository.

Provides async database operations for signal feeds.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import SignalFeed
from utils.log import logger


class SignalFeedRepositoryAsync:
    """Async repository for signal feed operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, feed: SignalFeed) -> SignalFeed:
        """
        Create a new signal feed.

        Args:
            feed: SignalFeed object to create.

        Returns:
            The created SignalFeed object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(feed)
            await self.session.flush()
            await self.session.refresh(feed)
            return feed
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating signal feed: {e}")
            raise

    async def get_by_id(self, feed_id: uuid.UUID) -> SignalFeed | None:
        """
        Retrieve a signal feed by ID.

        Args:
            feed_id: UUID of the signal feed.

        Returns:
            SignalFeed if found, None otherwise.
        """
        try:
            query = select(SignalFeed).filter(SignalFeed.id == feed_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting signal feed by id: {e}")
            return None

    async def get_by_source_id(self, source_id: uuid.UUID) -> SignalFeed | None:
        """
        Retrieve a signal feed by source ID.

        In V1, there is a 1:1 relationship between source and feed.

        Args:
            source_id: UUID of the signal source.

        Returns:
            SignalFeed if found, None otherwise.
        """
        try:
            query = select(SignalFeed).filter(SignalFeed.source_id == source_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting signal feed by source id: {e}")
            return None

    async def update_last_capture(
        self,
        feed_id: uuid.UUID,
        captured_at: datetime,
    ) -> SignalFeed | None:
        """
        Update the last capture timestamp and increment capture count.

        Args:
            feed_id: UUID of the signal feed.
            captured_at: Timestamp of the capture.

        Returns:
            Updated SignalFeed if found, None otherwise.
        """
        try:
            feed = await self.get_by_id(feed_id)
            if not feed:
                return None

            feed.last_capture_at = captured_at
            feed.capture_count = feed.capture_count + 1

            await self.session.flush()
            await self.session.refresh(feed)
            return feed
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating signal feed last capture: {e}")
            raise

    async def delete_by_source_id(self, source_id: uuid.UUID) -> bool:
        """
        Delete a signal feed by its source ID.

        Args:
            source_id: UUID of the signal source.

        Returns:
            True if deleted, False if not found.
        """
        try:
            feed = await self.get_by_source_id(source_id)
            if not feed:
                return False

            await self.session.delete(feed)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting signal feed by source id: {e}")
            raise
