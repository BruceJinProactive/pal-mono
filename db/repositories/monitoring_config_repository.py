"""Monitoring Config Repository.

Provides async database operations for monitoring configurations.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from db.tables import MonitoringConfig
from utils.log import logger


class MonitoringConfigRepositoryAsync:
    """Async repository for monitoring configuration operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, config: MonitoringConfig) -> MonitoringConfig:
        """
        Create a new monitoring configuration.

        Args:
            config: MonitoringConfig object to create.

        Returns:
            The created MonitoringConfig object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(config)
            await self.session.flush()
            await self.session.refresh(config)
            return config
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating monitoring config: {e}")
            raise

    async def get_by_id(self, config_id: uuid.UUID) -> MonitoringConfig | None:
        """
        Retrieve a monitoring configuration by ID.

        Args:
            config_id: UUID of the monitoring configuration.

        Returns:
            MonitoringConfig if found, None otherwise.
        """
        try:
            query = select(MonitoringConfig).filter(MonitoringConfig.id == config_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting monitoring config by id: {e}")
            return None

    async def get_by_project(
        self,
        project_id: uuid.UUID,
        enabled: bool | None = None,
        signal_source_id: uuid.UUID | None = None,
    ) -> list[MonitoringConfig]:
        """
        Get all monitoring configurations for a project.

        Args:
            project_id: Project UUID.
            enabled: Optional filter by enabled status.
            signal_source_id: Optional filter by signal source.

        Returns:
            List of MonitoringConfig objects.
        """
        try:
            query = select(MonitoringConfig).filter(
                MonitoringConfig.project_id == project_id
            )

            if enabled is not None:
                query = query.filter(MonitoringConfig.enabled == enabled)

            if signal_source_id is not None:
                query = query.filter(
                    MonitoringConfig.signal_source_id == signal_source_id
                )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting monitoring configs by project: {e}")
            return []

    async def get_by_name(
        self, project_id: uuid.UUID, name: str
    ) -> MonitoringConfig | None:
        """
        Get monitoring configuration by name within a project.

        Args:
            project_id: Project UUID.
            name: Configuration name.

        Returns:
            MonitoringConfig if found, None otherwise.
        """
        try:
            query = select(MonitoringConfig).filter(
                MonitoringConfig.project_id == project_id,
                MonitoringConfig.name == name,
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting monitoring config by name: {e}")
            return None

    async def update(self, config_id: uuid.UUID, **kwargs) -> MonitoringConfig | None:
        """
        Update a monitoring configuration by ID.

        Args:
            config_id: UUID of the monitoring configuration.
            **kwargs: Fields to update.

        Returns:
            Updated MonitoringConfig if found, None otherwise.
        """
        try:
            config = await self.get_by_id(config_id)
            if not config:
                return None

            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                    # Mark JSONB fields as modified to ensure SQLAlchemy tracks changes
                    if key == "rules":
                        attributes.flag_modified(config, "rules")

            await self.session.flush()
            await self.session.refresh(config)
            return config
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating monitoring config: {e}")
            raise

    async def delete(self, config_id: uuid.UUID) -> bool:
        """
        Delete a monitoring configuration by ID.

        Args:
            config_id: UUID of the monitoring configuration.

        Returns:
            True if deleted, False if not found.
        """
        try:
            config = await self.get_by_id(config_id)
            if not config:
                return False

            await self.session.delete(config)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting monitoring config: {e}")
            raise
