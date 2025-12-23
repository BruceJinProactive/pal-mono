"""Signal Source Repository.

Provides async database operations for signal sources.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import SignalSource
from utils.log import logger


class SignalSourceRepositoryAsync:
    """Async repository for signal source operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, source: SignalSource) -> SignalSource:
        """
        Create a new signal source.

        Args:
            source: SignalSource object to create.

        Returns:
            The created SignalSource object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(source)
            await self.session.flush()
            await self.session.refresh(source)
            return source
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating signal source: {e}")
            raise

    async def get_by_id(self, source_id: uuid.UUID) -> SignalSource | None:
        """
        Retrieve a signal source by ID.

        Args:
            source_id: UUID of the signal source.

        Returns:
            SignalSource if found, None otherwise.
        """
        try:
            query = select(SignalSource).filter(SignalSource.id == source_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting signal source by id: {e}")
            return None

    async def get_by_account(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> list[SignalSource]:
        """
        Get all signal sources visible to a project.

        Returns sources where:
        - account_id matches AND
        - (project_id IS NULL (account-level) OR project_id matches (project-level))

        Args:
            account_id: Account UUID.
            project_id: Optional project UUID to filter by.

        Returns:
            List of SignalSource objects.
        """
        try:
            query = select(SignalSource).filter(SignalSource.account_id == account_id)

            if project_id is not None:
                # Include account-level sources (project_id is NULL) and
                # project-level sources for this specific project
                query = query.filter(
                    or_(
                        SignalSource.project_id.is_(None),
                        SignalSource.project_id == project_id,
                    )
                )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting signal sources by account: {e}")
            return []

    async def update(self, source_id: uuid.UUID, **kwargs) -> SignalSource | None:
        """
        Update a signal source by ID.

        Args:
            source_id: UUID of the signal source.
            **kwargs: Fields to update.

        Returns:
            Updated SignalSource if found, None otherwise.
        """
        try:
            source = await self.get_by_id(source_id)
            if not source:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(source, key):
                    setattr(source, key, value)

            await self.session.flush()
            await self.session.refresh(source)
            return source
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating signal source: {e}")
            raise

    async def delete(self, source_id: uuid.UUID) -> bool:
        """
        Delete a signal source by ID.

        Args:
            source_id: UUID of the signal source.

        Returns:
            True if deleted, False if not found.
        """
        try:
            source = await self.get_by_id(source_id)
            if not source:
                return False

            await self.session.delete(source)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting signal source: {e}")
            raise
