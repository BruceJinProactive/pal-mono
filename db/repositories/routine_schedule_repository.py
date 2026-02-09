"""Routine Schedule Repository.

Provides async database operations for routine schedules.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TypedDict

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.routine_executions import RoutineExecution
from db.tables.routine_schedules import RoutineSchedule
from db.tables.routines import Routine
from db.tables.types import ExecutionStatus, RoutineFrequency
from utils.log import logger


class ScheduleNeedingExecution(TypedDict):
    """Result type for schedules needing execution replenishment."""

    schedule_id: uuid.UUID
    routine_id: uuid.UUID
    project_id: uuid.UUID
    future_pending_count: int


class RoutineScheduleRepositoryAsync:
    """Async repository for routine schedule operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_schedule(
        self,
        routine_id: uuid.UUID,
        frequency: RoutineFrequency,
        start_time: time,
        end_time: time,
        timezone: str = "America/Los_Angeles",
        days_of_week: list[int] | None = None,
        day_of_month: int | None = None,
        interval_hours: int | None = None,
        effective_from: date | None = None,
        effective_until: date | None = None,
        is_active: bool = True,
    ) -> RoutineSchedule:
        """
        Create a new schedule for a routine.

        Args:
            routine_id: Parent routine ID
            frequency: Frequency of the schedule
            start_time: Time when routine is due
            end_time: Grace period end time
            timezone: Timezone for the schedule
            days_of_week: For weekly: list of days [0=Sun, 1=Mon, ..., 6=Sat]
            day_of_month: For monthly: day of month (1-31)
            interval_hours: For custom: hours between executions
            effective_from: Optional start date
            effective_until: Optional end date
            is_active: Whether the schedule is active

        Returns:
            The created RoutineSchedule object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            schedule = RoutineSchedule(
                routine_id=routine_id,
                frequency=frequency,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone,
                days_of_week=days_of_week,
                day_of_month=day_of_month,
                interval_hours=interval_hours,
                effective_from=effective_from,
                effective_until=effective_until,
                is_active=is_active,
            )
            self.session.add(schedule)
            await self.session.flush()
            await self.session.refresh(schedule)
            return schedule
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating schedule: {e}")
            raise

    async def get_schedule_by_id(
        self, schedule_id: uuid.UUID
    ) -> RoutineSchedule | None:
        """
        Retrieve a schedule by its ID.

        Args:
            schedule_id: UUID of the schedule

        Returns:
            RoutineSchedule object if found, None otherwise
        """
        try:
            stmt = select(RoutineSchedule).where(RoutineSchedule.id == schedule_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting schedule by id: {e}")
            return None

    async def list_schedules_by_routine(
        self,
        routine_id: uuid.UUID,
        is_active: bool | None = None,
    ) -> list[RoutineSchedule]:
        """
        List all schedules for a specific routine.

        Args:
            routine_id: UUID of the routine
            is_active: Optional filter for active status

        Returns:
            List of RoutineSchedule objects
        """
        try:
            stmt = select(RoutineSchedule).where(
                RoutineSchedule.routine_id == routine_id
            )

            if is_active is not None:
                stmt = stmt.where(RoutineSchedule.is_active == is_active)

            stmt = stmt.order_by(RoutineSchedule.created_at.desc())
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing schedules by routine: {e}")
            return []

    async def list_active_schedules(self) -> list[RoutineSchedule]:
        """
        List all active schedules across all routines.

        Used by the scheduler to determine which executions to generate.

        Returns:
            List of active RoutineSchedule objects
        """
        try:
            stmt = (
                select(RoutineSchedule)
                .where(RoutineSchedule.is_active == True)  # noqa: E712
                .order_by(RoutineSchedule.routine_id)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing active schedules: {e}")
            return []

    async def update_schedule(
        self,
        schedule_id: uuid.UUID,
        frequency: RoutineFrequency | None = None,
        start_time: time | None = None,
        end_time: time | None = None,
        timezone: str | None = None,
        days_of_week: list[int] | None = None,
        day_of_month: int | None = None,
        interval_hours: int | None = None,
        effective_from: date | None = None,
        effective_until: date | None = None,
        is_active: bool | None = None,
    ) -> RoutineSchedule | None:
        """
        Update a schedule by its ID.

        Args:
            schedule_id: UUID of the schedule
            frequency: Optional new frequency
            start_time: Optional new start time
            end_time: Optional new end time
            timezone: Optional new timezone
            days_of_week: Optional new days of week
            day_of_month: Optional new day of month
            interval_hours: Optional new interval hours
            effective_from: Optional new effective from date
            effective_until: Optional new effective until date
            is_active: Optional new active status

        Returns:
            Updated RoutineSchedule object if found, None otherwise
        """
        try:
            schedule = await self.get_schedule_by_id(schedule_id)
            if not schedule:
                return None

            if frequency is not None:
                schedule.frequency = frequency
            if start_time is not None:
                schedule.start_time = start_time
            if end_time is not None:
                schedule.end_time = end_time
            if timezone is not None:
                schedule.timezone = timezone
            if days_of_week is not None:
                schedule.days_of_week = days_of_week
            if day_of_month is not None:
                schedule.day_of_month = day_of_month
            if interval_hours is not None:
                schedule.interval_hours = interval_hours
            if effective_from is not None:
                schedule.effective_from = effective_from
            if effective_until is not None:
                schedule.effective_until = effective_until
            if is_active is not None:
                schedule.is_active = is_active

            await self.session.flush()
            await self.session.refresh(schedule)
            return schedule
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating schedule: {e}")
            return None

    async def delete_schedule(self, schedule_id: uuid.UUID) -> bool:
        """
        Delete a schedule by its ID.

        Args:
            schedule_id: UUID of the schedule

        Returns:
            True if deleted, False if not found
        """
        try:
            schedule = await self.get_schedule_by_id(schedule_id)
            if not schedule:
                return False

            await self.session.delete(schedule)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting schedule: {e}")
            return False

    async def delete_schedules_by_routine(self, routine_id: uuid.UUID) -> int:
        """
        Delete all schedules for a routine.

        Args:
            routine_id: UUID of the routine

        Returns:
            Number of schedules deleted
        """
        try:
            schedules = await self.list_schedules_by_routine(routine_id)
            count = len(schedules)
            for schedule in schedules:
                await self.session.delete(schedule)
            await self.session.flush()
            return count
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting schedules by routine: {e}")
            return 0

    async def list_schedules_by_routine_ids(
        self,
        routine_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[RoutineSchedule]]:
        """
        List all schedules for multiple routines in a single query.

        Args:
            routine_ids: List of routine UUIDs

        Returns:
            Dict mapping routine_id to list of RoutineSchedule objects
        """
        try:
            if not routine_ids:
                return {}

            stmt = (
                select(RoutineSchedule)
                .where(RoutineSchedule.routine_id.in_(routine_ids))
                .order_by(RoutineSchedule.routine_id, RoutineSchedule.created_at.desc())
            )
            result = await self.session.execute(stmt)
            schedules = list(result.scalars().all())

            # Group schedules by routine_id
            schedules_by_routine: dict[uuid.UUID, list[RoutineSchedule]] = {
                routine_id: [] for routine_id in routine_ids
            }
            for schedule in schedules:
                schedules_by_routine[schedule.routine_id].append(schedule)

            return schedules_by_routine
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing schedules by routine ids: {e}")
            return {routine_id: [] for routine_id in routine_ids}

    async def find_schedules_needing_executions(
        self,
        pending_threshold: int,
        now_utc: datetime,
    ) -> list[ScheduleNeedingExecution]:
        """
        Find active schedules with fewer than threshold future pending executions.

        This query:
        1. Joins RoutineSchedule -> Routine -> RoutineExecution
        2. Counts only future pending executions (scheduled_start > now_utc)
        3. Filters for active schedules and routines
        4. Returns schedules where future_pending_count < threshold

        Used by the scheduler to discover which schedules need execution replenishment.

        Args:
            pending_threshold: Minimum number of future pending executions required
            now_utc: Current UTC time for future execution filtering

        Returns:
            List of ScheduleNeedingExecution dicts with schedule metadata
        """
        try:
            stmt = (
                select(
                    RoutineSchedule.id.label("schedule_id"),
                    Routine.id.label("routine_id"),
                    Routine.project_id,
                    func.count(RoutineExecution.id).label("future_pending_count"),
                )
                .select_from(RoutineSchedule)
                .join(Routine, RoutineSchedule.routine_id == Routine.id)
                .outerjoin(
                    RoutineExecution,
                    and_(
                        RoutineExecution.schedule_id == RoutineSchedule.id,
                        RoutineExecution.status == ExecutionStatus.pending,
                        RoutineExecution.scheduled_start > now_utc,
                    ),
                )
                .where(
                    and_(
                        RoutineSchedule.is_active == True,  # noqa: E712
                        Routine.is_active == True,  # noqa: E712
                    )
                )
                .group_by(
                    RoutineSchedule.id,
                    Routine.id,
                    Routine.project_id,
                )
                .having(func.count(RoutineExecution.id) < pending_threshold)
            )

            result = await self.session.execute(stmt)
            rows = result.all()

            # Convert SQLAlchemy Row objects to TypedDict
            return [
                ScheduleNeedingExecution(
                    schedule_id=row.schedule_id,
                    routine_id=row.routine_id,
                    project_id=row.project_id,
                    future_pending_count=row.future_pending_count,
                )
                for row in rows
            ]
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error finding schedules needing executions: {e}")
            return []
