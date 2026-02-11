"""Signal Source Repository.

Provides async database operations for signal sources.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import SignalFeed, SignalSource
from db.tables.accounts import Account
from db.tables.types import SignalType
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

    async def get_by_camera_id(
        self,
        project_id: uuid.UUID,
        camera_id: str,
    ) -> SignalSource | None:
        """
        Get signal source by camera_id within a project.

        Args:
            project_id: Project UUID.
            camera_id: Camera identifier from config.

        Returns:
            SignalSource if found, None otherwise.
        """
        try:
            query = select(SignalSource).filter(
                SignalSource.project_id == project_id,
                SignalSource.config["camera_id"].astext == camera_id,
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting signal source by camera_id: {e}")
            return None

    async def camera_id_exists(
        self,
        project_id: uuid.UUID,
        camera_id: str,
        exclude_source_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Check if camera_id already exists in project.

        Args:
            project_id: Project UUID.
            camera_id: Camera identifier to check.
            exclude_source_id: Optional source ID to exclude (for updates).

        Returns:
            True if camera_id exists, False otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            query = select(SignalSource).filter(
                SignalSource.project_id == project_id,
                SignalSource.config["camera_id"].astext == camera_id,
            )
            if exclude_source_id:
                query = query.filter(SignalSource.id != exclude_source_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none() is not None
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error checking camera_id existence: {e}")
            raise

    async def get_cameras_with_feeds_by_account_names(
        self, account_names: list[str] | None = None
    ) -> list[tuple[SignalSource, SignalFeed | None, str | None]]:
        """
        Get all camera-type signal sources with their feeds, optionally filtered by account names.

        Args:
            account_names: Optional list of account names to filter by.

        Returns:
            List of tuples containing (SignalSource, SignalFeed or None, account_name or None).
            Returns all cameras if account_names is None.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            # Build base query for cameras with eager loading of feeds
            query = (
                select(SignalSource, SignalFeed, Account.name)
                .join(Account, SignalSource.account_id == Account.id)
                .outerjoin(SignalFeed, SignalSource.id == SignalFeed.source_id)
                .where(SignalSource.signal_type == SignalType.camera)
            )

            # Filter by account names if provided
            if account_names:
                query = query.where(Account.name.in_(account_names))

            result = await self.session.execute(query)
            # Convert Row objects to tuples for type consistency
            return [(row[0], row[1], row[2]) for row in result.all()]

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting cameras with feeds by accounts: {e}")
            raise
