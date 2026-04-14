"""Monitoring Run Repository.

Provides async database operations for monitoring runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Row, case, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import MonitoringConfig, MonitoringRun
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

            if result_filter is not None:
                # Coalesce with JSONB field so pre-migration rows (result IS NULL) still match
                query = query.filter(
                    func.coalesce(
                        MonitoringRun.result,
                        MonitoringRun.evaluation_result["result"].astext,
                    )
                    == result_filter
                )

            # Order by started_at descending (most recent first)
            query = query.order_by(MonitoringRun.started_at.desc())

            result = await self.session.execute(query)
            return list(result.scalars().all())
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

    async def delete_runs_by_config_id(self, config_id: uuid.UUID) -> int:
        """
        Delete all monitoring runs for a given config using a bulk SQL delete.

        Args:
            config_id: UUID of the monitoring configuration.

        Returns:
            Number of rows deleted.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            result = await self.session.execute(
                delete(MonitoringRun).where(
                    MonitoringRun.monitoring_config_id == config_id
                )
            )
            await self.session.flush()
            return result.rowcount or 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting monitoring runs by config: {e}")
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

    async def get_summary_by_tags(
        self,
        project_id: uuid.UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Row[tuple[str, int, int, int, int]]]:
        """
        Aggregate monitoring run results grouped by tag.

        Unnests the tags array from enabled configs, joins with runs,
        and returns per-tag counts of pass/fail/error results.

        Args:
            project_id: Project UUID to filter configs.
            start_date: Optional start of time range (inclusive).
            end_date: Optional end of time range (exclusive).

        Returns:
            List of rows with (tag, total_runs, pass_count, fail_count, error_count).
        """
        try:
            tag = func.unnest(MonitoringConfig.tags).label("tag")

            result_col = func.coalesce(
                MonitoringRun.result,
                MonitoringRun.evaluation_result["result"].astext,
            )

            query = (
                select(
                    tag,
                    func.count().label("total_runs"),
                    func.count(case((result_col == "pass", 1))).label("pass_count"),
                    func.count(case((result_col == "fail", 1))).label("fail_count"),
                    func.count(case((result_col == "error", 1))).label("error_count"),
                )
                .select_from(MonitoringConfig)
                .join(
                    MonitoringRun,
                    MonitoringRun.monitoring_config_id == MonitoringConfig.id,
                )
                .where(
                    MonitoringConfig.project_id == project_id,
                    MonitoringConfig.enabled.is_(True),
                    func.cardinality(MonitoringConfig.tags) > 0,
                    result_col != "skipped",
                )
                .group_by(tag)
                .order_by(func.count(case((result_col == "fail", 1))).desc())
            )

            if start_date is not None:
                query = query.where(MonitoringRun.started_at >= start_date)

            if end_date is not None:
                query = query.where(MonitoringRun.started_at < end_date)

            result = await self.session.execute(query)
            return list(result.all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting monitoring summary by tags: {e}")
            return []
