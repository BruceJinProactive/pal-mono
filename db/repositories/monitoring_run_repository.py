"""Monitoring Run Repository.

Provides async database operations for monitoring runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import MonitoringRun
from utils.log import logger


class MonitoringRunRepositoryAsync:
    """Async repository for monitoring run operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, run: MonitoringRun) -> MonitoringRun:
        """
        Create a new monitoring run.

        Args:
            run: MonitoringRun object to create.

        Returns:
            The created MonitoringRun object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(run)
            await self.session.flush()
            await self.session.refresh(run)
            return run
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating monitoring run: {e}")
            raise

    async def get_by_id(self, run_id: uuid.UUID) -> MonitoringRun | None:
        """
        Retrieve a monitoring run by ID.

        Args:
            run_id: UUID of the monitoring run.

        Returns:
            MonitoringRun if found, None otherwise.
        """
        try:
            query = select(MonitoringRun).filter(MonitoringRun.id == run_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting monitoring run by id: {e}")
            return None

    async def get_by_config(
        self,
        monitoring_config_id: uuid.UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        result_filter: str | None = None,
    ) -> list[MonitoringRun]:
        """
        Get all monitoring runs for a configuration.

        Args:
            monitoring_config_id: Monitoring config UUID.
            start_date: Optional filter for runs after this date.
            end_date: Optional filter for runs before this date.
            result_filter: Optional filter by result ('pass', 'fail', 'error').

        Returns:
            List of MonitoringRun objects.
        """
        try:
            query = select(MonitoringRun).filter(
                MonitoringRun.monitoring_config_id == monitoring_config_id
            )

            if start_date is not None:
                query = query.filter(MonitoringRun.started_at >= start_date)

            if end_date is not None:
                query = query.filter(MonitoringRun.started_at <= end_date)

            # Order by started_at descending (most recent first)
            query = query.order_by(MonitoringRun.started_at.desc())

            result = await self.session.execute(query)
            runs = list(result.scalars().all())

            # Apply result filter in Python since it's stored in JSONB
            if result_filter and runs:
                runs = [
                    run
                    for run in runs
                    if run.evaluation_result.get("result") == result_filter
                ]

            return runs
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting monitoring runs by config: {e}")
            return []

    async def update(self, run_id: uuid.UUID, **kwargs) -> MonitoringRun | None:
        """
        Update a monitoring run by ID.

        Note: Runs should generally be immutable after creation,
        but this allows updating completed_at, evaluation_result, error_message.

        Args:
            run_id: UUID of the monitoring run.
            **kwargs: Fields to update.

        Returns:
            Updated MonitoringRun if found, None otherwise.
        """
        try:
            run = await self.get_by_id(run_id)
            if not run:
                return None

            for key, value in kwargs.items():
                if hasattr(run, key):
                    setattr(run, key, value)

            await self.session.flush()
            await self.session.refresh(run)
            return run
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating monitoring run: {e}")
            raise

    async def delete(self, run_id: uuid.UUID) -> bool:
        """
        Delete a monitoring run by ID.

        Args:
            run_id: UUID of the monitoring run.

        Returns:
            True if deleted successfully, False if not found.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            run = await self.get_by_id(run_id)
            if not run:
                return False

            await self.session.delete(run)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting monitoring run: {e}")
            raise

    async def delete_batch(self, run_ids: list[uuid.UUID]) -> dict[str, int]:
        """
        Delete multiple monitoring runs by IDs.

        Args:
            run_ids: List of run UUIDs to delete.

        Returns:
            Dictionary with 'deleted' count and 'not_found' count.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            deleted_count = 0
            not_found_count = 0

            for run_id in run_ids:
                run = await self.get_by_id(run_id)
                if run:
                    await self.session.delete(run)
                    deleted_count += 1
                else:
                    not_found_count += 1

            await self.session.flush()
            return {"deleted": deleted_count, "not_found": not_found_count}
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting monitoring runs in batch: {e}")
            raise
