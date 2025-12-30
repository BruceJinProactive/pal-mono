"""
Routine Schedule Service Implementation

Business logic for routine schedule operations.
Authorization is handled in the API layer.
"""

from datetime import time
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    CreateScheduleRequest,
    ListSchedulesResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
)
from db.repositories import RoutineRepositoryAsync, RoutineScheduleRepositoryAsync
from db.tables.routine_schedules import RoutineSchedule
from services.auth_types import UserContext


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

    await session.commit()

    return _build_schedule_response(schedule)


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

    await session.commit()

    return _build_schedule_response(updated)


async def delete_schedule(
    schedule_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a schedule.
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

    deleted = await schedule_repo.delete_schedule(schedule_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete schedule {schedule_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()
