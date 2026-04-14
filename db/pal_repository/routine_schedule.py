from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.routine_schedule import RoutineScheduleData
from db.tables.routine_schedules import RoutineSchedule
from db.tables.types import RoutineFrequency
from utils.log import logger


def _to_data(row: RoutineSchedule) -> RoutineScheduleData:
    """Convert an ORM RoutineSchedule to a RoutineScheduleData."""
    return RoutineScheduleData(
        id=row.id,
        routine_id=row.routine_id,
        frequency=row.frequency.value if row.frequency else "",
        start_time=row.start_time,
        end_time=row.end_time,
        timezone=row.timezone,
        days_of_week=tuple(row.days_of_week) if row.days_of_week is not None else None,
        day_of_month=row.day_of_month,
        interval_hours=row.interval_hours,
        effective_from=row.effective_from,
        effective_until=row.effective_until,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class RoutineScheduleRepository:
    """Async-only repository for RoutineSchedule records.

    All methods return ``RoutineScheduleData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, schedule_id: uuid.UUID) -> RoutineScheduleData | None:
        """Retrieve a single schedule by its primary key."""
        try:
            result = await self.session.execute(
                select(RoutineSchedule).filter(RoutineSchedule.id == schedule_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving routine schedule by ID")
            raise

    async def list_by_routine_id(
        self, routine_id: uuid.UUID
    ) -> list[RoutineScheduleData]:
        """List all schedules for a given routine."""
        try:
            result = await self.session.execute(
                select(RoutineSchedule)
                .filter(RoutineSchedule.routine_id == routine_id)
                .order_by(RoutineSchedule.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing routine schedules by routine ID")
            raise

    async def list_active_by_routine_id(
        self, routine_id: uuid.UUID
    ) -> list[RoutineScheduleData]:
        """List only active schedules for a given routine."""
        try:
            result = await self.session.execute(
                select(RoutineSchedule)
                .filter(
                    RoutineSchedule.routine_id == routine_id,
                    RoutineSchedule.is_active.is_(True),
                )
                .order_by(RoutineSchedule.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing active routine schedules")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: RoutineScheduleData) -> None:
        """Create a new routine schedule.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = RoutineSchedule(
                id=record.id,
                routine_id=record.routine_id,
                frequency=RoutineFrequency(record.frequency),
                start_time=record.start_time,
                end_time=record.end_time,
                timezone=record.timezone,
                days_of_week=(
                    list(record.days_of_week)
                    if record.days_of_week is not None
                    else None
                ),
                day_of_month=record.day_of_month,
                interval_hours=record.interval_hours,
                effective_from=record.effective_from,
                effective_until=record.effective_until,
                is_active=record.is_active,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating routine schedule: {e}")
            raise

    async def delete(self, schedule_id: uuid.UUID) -> RoutineScheduleData | None:
        """Delete a routine schedule by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(RoutineSchedule).filter(RoutineSchedule.id == schedule_id)
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
            logger.error(f"Error deleting routine schedule: {e}")
            raise
