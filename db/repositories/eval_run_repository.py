"""Eval Run Repository.

Provides async database operations for evaluation runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import EvalRun
from utils.log import logger


class EvalRunRepositoryAsync:
    """Async repository for eval run operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, run: EvalRun) -> EvalRun:
        """Create a new eval run.

        Args:
            run: EvalRun object to create.

        Returns:
            The created EvalRun object.

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
            logger.error(f"Error creating eval run: {e}")
            raise

    async def get_by_id(self, run_id: uuid.UUID) -> EvalRun | None:
        """Retrieve an eval run by ID.

        Args:
            run_id: UUID of the eval run.

        Returns:
            EvalRun if found, None otherwise.
        """
        try:
            query = select(EvalRun).filter(EvalRun.id == run_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting eval run by id: {e}")
            return None

    async def get_all(
        self,
        *,
        status: str | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[EvalRun]:
        """Get eval runs with optional filters.

        Args:
            status: Optional filter by run status (e.g. 'running', 'pending').
            project_id: Optional filter by project UUID.
            limit: Maximum number of runs to return.

        Returns:
            List of EvalRun objects ordered by created_at descending.
        """
        try:
            query = select(EvalRun)

            if status is not None:
                query = query.filter(EvalRun.status == status)
            if project_id is not None:
                query = query.filter(EvalRun.project_id == project_id)

            query = query.order_by(EvalRun.created_at.desc()).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting eval runs: {e}")
            return []

    async def get_by_project(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[EvalRun]:
        """Get all eval runs for a project.

        Args:
            project_id: Project UUID.
            status: Optional filter by run status (e.g. 'pending', 'running', 'completed', 'failed').
            start_date: Optional filter for runs with started_at >= this date.
            end_date: Optional filter for runs with started_at <= this date.

        Returns:
            List of EvalRun objects ordered by created_at descending (most recent first).
        """
        try:
            query = select(EvalRun).filter(EvalRun.project_id == project_id)

            if status is not None:
                query = query.filter(EvalRun.status == status)

            if start_date is not None:
                query = query.filter(EvalRun.started_at >= start_date)

            if end_date is not None:
                query = query.filter(EvalRun.started_at <= end_date)

            query = query.order_by(EvalRun.created_at.desc())

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting eval runs by project: {e}")
            return []

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> EvalRun | None:
        """Update the status and lifecycle timestamps of an eval run.

        Args:
            run_id: UUID of the eval run.
            status: New status value (e.g. 'running', 'completed', 'failed').
            started_at: Optional timestamp to set as started_at.
            completed_at: Optional timestamp to set as completed_at.
            error_message: Optional error message to record.

        Returns:
            Updated EvalRun if found, None if the run does not exist.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            run = await self.get_by_id(run_id)
            if not run:
                return None

            run.status = status
            if started_at is not None:
                run.started_at = started_at
            if completed_at is not None:
                run.completed_at = completed_at
            if error_message is not None:
                run.error_message = error_message

            await self.session.flush()
            await self.session.refresh(run)
            return run
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating eval run status: {e}")
            raise

    async def update_counts(
        self,
        run_id: uuid.UUID,
        *,
        scenario_count: int | None = None,
        passed_count: int | None = None,
        failed_count: int | None = None,
        overall_score: float | None = None,
    ) -> EvalRun | None:
        """Update scenario counters and overall score for an eval run.

        Note: This method may be called concurrently by scenario workers during
        a run. Callers are responsible for serialising updates at the service
        layer (e.g. SELECT … FOR UPDATE) to avoid lost writes; no locking is
        implemented here.

        Args:
            run_id: UUID of the eval run.
            scenario_count: Optional total number of scenarios.
            passed_count: Optional number of passing scenarios.
            failed_count: Optional number of failing scenarios.
            overall_score: Optional aggregate score (0.0-1.0).

        Returns:
            Updated EvalRun if found, None if the run does not exist.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            run = await self.get_by_id(run_id)
            if not run:
                return None

            if scenario_count is not None:
                run.scenario_count = scenario_count
            if passed_count is not None:
                run.passed_count = passed_count
            if failed_count is not None:
                run.failed_count = failed_count
            if overall_score is not None:
                run.overall_score = overall_score

            await self.session.flush()
            await self.session.refresh(run)
            return run
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating eval run counts: {e}")
            raise

    async def update(self, run_id: uuid.UUID, **kwargs: object) -> EvalRun | None:
        """Update an eval run by ID using arbitrary keyword arguments.

        Args:
            run_id: UUID of the eval run.
            **kwargs: Fields to update (only fields that exist on EvalRun are applied).

        Returns:
            Updated EvalRun if found, None if the run does not exist.

        Raises:
            SQLAlchemyError: If there is a database error.
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
            logger.error(f"Error updating eval run: {e}")
            raise
