"""Routine Execution Repository.

Provides async database operations for routine executions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.routine_executions import RoutineExecution
from db.tables.routines import Routine
from db.tables.types import ExecutionStatus
from utils.log import logger


class RoutineExecutionRepositoryAsync:
    """Async repository for routine execution operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_execution(
        self,
        routine_id: uuid.UUID,
        schedule_id: uuid.UUID,
        scheduled_start: datetime,
        scheduled_end: datetime,
        status: ExecutionStatus = ExecutionStatus.pending,
        assigned_user_id: uuid.UUID | None = None,
    ) -> RoutineExecution:
        """
        Create a new routine execution.

        Args:
            routine_id: Parent routine ID
            schedule_id: Parent schedule ID
            scheduled_start: When the routine becomes due
            scheduled_end: Grace period deadline
            status: Initial status (default: pending)
            assigned_user_id: Optional assigned user

        Returns:
            The created RoutineExecution object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            execution = RoutineExecution(
                routine_id=routine_id,
                schedule_id=schedule_id,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                status=status,
                assigned_user_id=assigned_user_id,
            )
            self.session.add(execution)
            await self.session.flush()
            await self.session.refresh(execution)
            return execution
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating execution: {e}")
            raise

    async def get_execution_by_id(
        self, execution_id: uuid.UUID
    ) -> RoutineExecution | None:
        """
        Retrieve an execution by its ID.

        Args:
            execution_id: UUID of the execution

        Returns:
            RoutineExecution object if found, None otherwise
        """
        try:
            stmt = select(RoutineExecution).where(RoutineExecution.id == execution_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting execution by id: {e}")
            return None

    async def list_executions_by_project(
        self,
        project_id: uuid.UUID,
        status: ExecutionStatus | None = None,
        scheduled_date: date | None = None,
        routine_id: uuid.UUID | None = None,
        timezone: str | None = None,
    ) -> list[RoutineExecution]:
        """
        List executions for routines belonging to a project.

        Args:
            project_id: UUID of the project (filters via routine.project_id)
            status: Optional filter by status
            scheduled_date: Optional filter by scheduled date (YYYY-MM-DD)
            routine_id: Optional filter by specific routine
            timezone: IANA timezone string for date filtering (e.g., 'America/Los_Angeles').
                     Required when scheduled_date is provided for correct timezone handling.

        Returns:
            List of RoutineExecution objects
        """
        try:
            # Join with Routine to filter by project_id
            stmt = (
                select(RoutineExecution)
                .join(Routine, RoutineExecution.routine_id == Routine.id)
                .where(Routine.project_id == project_id)
            )

            if status is not None:
                stmt = stmt.where(RoutineExecution.status == status)

            if scheduled_date is not None:
                # Use timezone-aware datetime range filtering to correctly match
                # executions that fall within the specified date in the given timezone.
                # This avoids issues where CAST(scheduled_start AS DATE) would use
                # the database server's timezone (UTC) instead of the project's timezone.
                try:
                    tz = ZoneInfo(timezone or "America/Los_Angeles")
                except ZoneInfoNotFoundError:
                    logger.warning(
                        f"Invalid timezone '{timezone}', falling back to America/Los_Angeles"
                    )
                    tz = ZoneInfo("America/Los_Angeles")

                # Calculate the start and end of the day in the project's timezone
                day_start = datetime.combine(scheduled_date, time.min, tzinfo=tz)
                day_end = datetime.combine(
                    scheduled_date + timedelta(days=1), time.min, tzinfo=tz
                )

                # Filter executions where scheduled_start falls within this day
                stmt = stmt.where(
                    and_(
                        RoutineExecution.scheduled_start >= day_start,
                        RoutineExecution.scheduled_start < day_end,
                    )
                )

            if routine_id is not None:
                stmt = stmt.where(RoutineExecution.routine_id == routine_id)

            stmt = stmt.order_by(RoutineExecution.scheduled_start.desc())
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing executions by project: {e}")
            return []

    async def list_executions_by_routine(
        self,
        routine_id: uuid.UUID,
        status: ExecutionStatus | None = None,
    ) -> list[RoutineExecution]:
        """
        List all executions for a specific routine.

        Args:
            routine_id: UUID of the routine
            status: Optional filter by status

        Returns:
            List of RoutineExecution objects
        """
        try:
            stmt = select(RoutineExecution).where(
                RoutineExecution.routine_id == routine_id
            )

            if status is not None:
                stmt = stmt.where(RoutineExecution.status == status)

            stmt = stmt.order_by(RoutineExecution.scheduled_start.desc())
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing executions by routine: {e}")
            return []

    async def list_executions_by_schedule(
        self,
        schedule_id: uuid.UUID,
    ) -> list[RoutineExecution]:
        """
        List all executions for a specific schedule.

        Args:
            schedule_id: UUID of the schedule

        Returns:
            List of RoutineExecution objects
        """
        try:
            stmt = (
                select(RoutineExecution)
                .where(RoutineExecution.schedule_id == schedule_id)
                .order_by(RoutineExecution.scheduled_start.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing executions by schedule: {e}")
            return []

    async def update_execution_status(
        self,
        execution_id: uuid.UUID,
        status: ExecutionStatus,
    ) -> RoutineExecution | None:
        """
        Update the status of an execution.

        Args:
            execution_id: UUID of the execution
            status: New status

        Returns:
            Updated RoutineExecution object if found, None otherwise
        """
        try:
            execution = await self.get_execution_by_id(execution_id)
            if not execution:
                return None

            execution.status = status
            await self.session.flush()
            await self.session.refresh(execution)
            return execution
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating execution status: {e}")
            return None

    async def update_execution(
        self,
        execution_id: uuid.UUID,
        status: ExecutionStatus | None = None,
        assigned_user_id: uuid.UUID | None = None,
    ) -> RoutineExecution | None:
        """
        Update an execution.

        Args:
            execution_id: UUID of the execution
            status: Optional new status
            assigned_user_id: Optional new assigned user

        Returns:
            Updated RoutineExecution object if found, None otherwise
        """
        try:
            execution = await self.get_execution_by_id(execution_id)
            if not execution:
                return None

            if status is not None:
                execution.status = status
            if assigned_user_id is not None:
                execution.assigned_user_id = assigned_user_id

            await self.session.flush()
            await self.session.refresh(execution)
            return execution
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating execution: {e}")
            return None

    async def list_pending_executions_past_deadline(
        self,
        cutoff_time: datetime,
    ) -> list[RoutineExecution]:
        """
        List pending executions that are past their deadline.

        Used to mark overdue executions as missed.

        Args:
            cutoff_time: Time to check against scheduled_end

        Returns:
            List of pending RoutineExecution objects past deadline
        """
        try:
            stmt = (
                select(RoutineExecution)
                .where(
                    and_(
                        RoutineExecution.status == ExecutionStatus.pending,
                        RoutineExecution.scheduled_end < cutoff_time,
                    )
                )
                .order_by(RoutineExecution.scheduled_start)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing pending executions past deadline: {e}")
            return []

    async def delete_execution(self, execution_id: uuid.UUID) -> bool:
        """
        Delete an execution by its ID.

        Args:
            execution_id: UUID of the execution

        Returns:
            True if deleted, False if not found
        """
        try:
            execution = await self.get_execution_by_id(execution_id)
            if not execution:
                return False

            await self.session.delete(execution)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting execution: {e}")
            return False

    async def delete_executions_by_routine(self, routine_id: uuid.UUID) -> int:
        """
        Delete all executions for a routine.

        Args:
            routine_id: UUID of the routine

        Returns:
            Number of executions deleted
        """
        try:
            stmt = delete(RoutineExecution).where(
                RoutineExecution.routine_id == routine_id
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting executions by routine: {e}")
            return 0

    async def delete_executions_by_schedule(self, schedule_id: uuid.UUID) -> int:
        """
        Delete all executions for a schedule.

        Args:
            schedule_id: UUID of the schedule

        Returns:
            Number of executions deleted
        """
        try:
            stmt = delete(RoutineExecution).where(
                RoutineExecution.schedule_id == schedule_id
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting executions by schedule: {e}")
            return 0
