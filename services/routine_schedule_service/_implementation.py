"""
Routine Schedule Service Implementation

Business logic for routine schedule operations.
Authorization is handled in the API layer.
"""

import asyncio
from datetime import datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    CreateScheduleRequest,
    ListSchedulesResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
)
from db.repositories import (
    ProjectRepositoryAsync,
    RoutineRepositoryAsync,
    RoutineScheduleRepositoryAsync,
)
from db.tables.routine_schedules import RoutineSchedule
from events import RoutineScheduleUpdated, publish_event
from services.auth_types import UserContext
from utils.log import logger


def _build_schedule_response(schedule: RoutineSchedule) -> ScheduleResponse:
    """Build a ScheduleResponse from database model."""
    return ScheduleResponse(
        id=schedule.id,
        routine_id=schedule.routine_id,
        frequency=schedule.frequency,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        timezone=schedule.timezone,
        days_of_week=schedule.days_of_week,
        day_of_month=schedule.day_of_month,
        interval_hours=schedule.interval_hours,
        effective_from=schedule.effective_from,
        effective_until=schedule.effective_until,
        is_active=schedule.is_active,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def _parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object.

    Args:
        time_str: Time string in HH:MM format

    Returns:
        time object

    Raises:
        HTTPException: If time format is invalid
    """
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError("Expected HH:MM format")
        hour = int(parts[0])
        minute = int(parts[1])
        return time(hour=hour, minute=minute)
    except (ValueError, IndexError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid time format '{time_str}': expected HH:MM (e.g., '09:00')",
            headers={"Content-Type": "application/json"},
        ) from e


async def create_schedule(
    routine_id: UUID,
    request: CreateScheduleRequest,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """
    Create a new schedule for a routine.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)
    schedule_repo = RoutineScheduleRepositoryAsync(session)

    # Verify routine exists
    routine = await routine_repo.get_routine_by_id(routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    schedule = await schedule_repo.create_schedule(
        routine_id=routine_id,
        frequency=request.frequency,
        start_time=_parse_time(request.start_time),
        end_time=_parse_time(request.end_time),
        timezone=request.timezone,
        days_of_week=request.days_of_week,
        day_of_month=request.day_of_month,
        interval_hours=request.interval_hours,
        effective_from=request.effective_from,
        effective_until=request.effective_until,
    )

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in sync _build_schedule_response would trigger greenlet errors)
    response = _build_schedule_response(schedule)

    await session.commit()

    return response


async def get_schedule(
    schedule_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """
    Get a schedule by ID.
    Authorization is handled in the API layer.
    """
    schedule_repo = RoutineScheduleRepositoryAsync(session)

    schedule = await schedule_repo.get_schedule_by_id(schedule_id)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
            headers={"Content-Type": "application/json"},
        )

    return _build_schedule_response(schedule)


async def list_schedules(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ListSchedulesResponse:
    """
    List all schedules for a routine.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)
    schedule_repo = RoutineScheduleRepositoryAsync(session)

    # Verify routine exists
    routine = await routine_repo.get_routine_by_id(routine_id)

    if not routine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine {routine_id} not found",
            headers={"Content-Type": "application/json"},
        )

    schedules = await schedule_repo.list_schedules_by_routine(routine_id)

    return ListSchedulesResponse(
        schedules=[_build_schedule_response(s) for s in schedules],
        total=len(schedules),
    )


_REGENERATION_FIELDS = {
    "frequency",
    "start_time",
    "end_time",
    "timezone",
    "days_of_week",
    "day_of_month",
    "interval_hours",
    "effective_from",
    "effective_until",
}


def _requires_regeneration(
    old_schedule: RoutineSchedule, request: UpdateScheduleRequest
) -> bool:
    """Check if the schedule update changes timing fields that require execution regeneration."""
    for field_name in _REGENERATION_FIELDS:
        new_value = getattr(request, field_name, None)
        if new_value is None:
            continue
        old_value = getattr(old_schedule, field_name)
        # Normalize frequency to .value strings so both sides are the same type
        if field_name == "frequency":
            old_value = old_value.value if old_value is not None else None
            new_value = new_value.value if hasattr(new_value, "value") else new_value
        # Normalize time fields: parse request "HH:MM" string into datetime.time
        if field_name in ("start_time", "end_time") and isinstance(new_value, str):
            new_value = _parse_time(new_value)
        if old_value != new_value:
            return True
    return False


async def update_schedule(
    schedule_id: UUID,
    request: UpdateScheduleRequest,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """
    Update a schedule.
    Authorization is handled in the API layer.
    """
    schedule_repo = RoutineScheduleRepositoryAsync(session)

    schedule = await schedule_repo.get_schedule_by_id(schedule_id)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Determine if timing fields changed before applying updates
    regeneration_needed = _requires_regeneration(schedule, request)

    # Load routine + project for event context before update
    routine_repo = RoutineRepositoryAsync(session)
    routine = await routine_repo.get_routine_by_id(schedule.routine_id)
    routine_id = schedule.routine_id

    project_id: UUID | None = None
    account_id: UUID | None = None
    if routine:
        project_id = routine.project_id
        project_repo = ProjectRepositoryAsync(session)
        project = await project_repo.get_project(routine.project_id)
        if project:
            account_id = project.account_id

    start_time = None
    if request.start_time is not None:
        start_time = _parse_time(request.start_time)

    end_time = None
    if request.end_time is not None:
        end_time = _parse_time(request.end_time)

    updated = await schedule_repo.update_schedule(
        schedule_id=schedule_id,
        frequency=request.frequency,
        start_time=start_time,
        end_time=end_time,
        timezone=request.timezone,
        days_of_week=request.days_of_week,
        day_of_month=request.day_of_month,
        interval_hours=request.interval_hours,
        effective_from=request.effective_from,
        effective_until=request.effective_until,
        is_active=request.is_active,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update schedule {schedule_id}",
            headers={"Content-Type": "application/json"},
        )

    # Build response before commit to avoid greenlet errors
    response = _build_schedule_response(updated)

    await session.commit()

    # Publish RoutineScheduleUpdated event (best-effort)
    if project_id and account_id:
        try:
            event = RoutineScheduleUpdated(
                routine_id=routine_id,
                schedule_id=schedule_id,
                project_id=project_id,
                account_id=account_id,
                requires_regeneration=regeneration_needed,
                updated_at=datetime.now(ZoneInfo("UTC")),
            )
            success = await publish_event(event)
            if not success:
                logger.warning(
                    f"Failed to publish RoutineScheduleUpdated event for schedule {schedule_id}",
                    extra={"schedule_id": str(schedule_id)},
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"Error publishing RoutineScheduleUpdated event for schedule {schedule_id}: {e}",
                exc_info=True,
                extra={"schedule_id": str(schedule_id)},
            )
    else:
        logger.warning(
            f"Skipping RoutineScheduleUpdated event for schedule {schedule_id}: "
            f"missing project_id={project_id} or account_id={account_id}",
            extra={"schedule_id": str(schedule_id)},
        )

    return response


async def delete_schedule(
    schedule_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a schedule.
    Authorization is handled in the API layer.

    Note: Each routine has one schedule. In most cases, use delete_routine instead
    to cascade-delete the routine, schedule, and all executions together.
    """
    schedule_repo = RoutineScheduleRepositoryAsync(session)

    schedule = await schedule_repo.get_schedule_by_id(schedule_id)

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
            headers={"Content-Type": "application/json"},
        )

    deleted = await schedule_repo.delete_schedule(schedule_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete schedule {schedule_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()
