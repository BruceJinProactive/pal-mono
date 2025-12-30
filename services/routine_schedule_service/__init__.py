"""
Routine Schedule Service

This service contains business logic for routine schedule operations.
Authorization is handled in the API layer.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    CreateScheduleRequest,
    ListSchedulesResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
)
from services.auth_types import UserContext

from . import _implementation

__all__ = [
    "create_schedule",
    "get_schedule",
    "list_schedules",
    "update_schedule",
    "delete_schedule",
]


async def create_schedule(
    routine_id: UUID,
    request: CreateScheduleRequest,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """
    Create a new schedule for a routine.

    Args:
        routine_id: UUID of the routine
        request: Request containing schedule data
        context: User authentication context
        session: Database session

    Returns:
        Created ScheduleResponse object
    """
    return await _implementation.create_schedule(routine_id, request, context, session)


async def get_schedule(
    schedule_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """
    Get a schedule by ID.

    Args:
        schedule_id: UUID of the schedule
        context: User authentication context
        session: Database session

    Returns:
        ScheduleResponse object
    """
    return await _implementation.get_schedule(schedule_id, context, session)


async def list_schedules(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ListSchedulesResponse:
    """
    List all schedules for a routine.

    Args:
        routine_id: UUID of the routine
        context: User authentication context
        session: Database session

    Returns:
        ListSchedulesResponse with schedules and total count
    """
    return await _implementation.list_schedules(routine_id, context, session)


async def update_schedule(
    schedule_id: UUID,
    request: UpdateScheduleRequest,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """
    Update a schedule.

    Args:
        schedule_id: UUID of the schedule
        request: Request containing update data
        context: User authentication context
        session: Database session

    Returns:
        Updated ScheduleResponse object
    """
    return await _implementation.update_schedule(schedule_id, request, context, session)


async def delete_schedule(
    schedule_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """
    Delete a schedule.

    Args:
        schedule_id: UUID of the schedule
        context: User authentication context
        session: Database session
    """
    await _implementation.delete_schedule(schedule_id, context, session)
