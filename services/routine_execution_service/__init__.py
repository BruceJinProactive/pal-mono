"""
Routine Execution Service

This service contains business logic for routine execution operations.
Authorization is handled in the API layer.
"""

import uuid
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    DeleteExecutionsResponse,
    DiscoveryResponse,
    ExecutionDetailResponse,
    GenerateExecutionsRequest,
    GenerateExecutionsResponse,
    ListExecutionsResponse,
)
from db.tables.types import ExecutionStatus
from services.auth_types import UserContext

from . import _implementation

__all__ = [
    "get_execution",
    "list_executions",
    "update_execution_status",
    # Internal API functions (called by Lambda/Scheduler)
    "discover_routines_needing_executions",
    "generate_executions",
    "delete_future_executions",
]


async def get_execution(
    execution_id: UUID,
    context: UserContext,
    session: AsyncSession,
    details: bool = False,
) -> ExecutionDetailResponse:
    """
    Get an execution by ID.

    Args:
        execution_id: UUID of the execution
        context: User authentication context
        session: Database session
        details: Include full routine and submission details

    Returns:
        ExecutionDetailResponse object
    """
    return await _implementation.get_execution(execution_id, context, session, details)


async def list_executions(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
    status_filter: ExecutionStatus | None = None,
    date_filter: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    routine_id: UUID | None = None,
    timezone: str | None = None,
    include_details: bool = False,
) -> ListExecutionsResponse:
    """
    List executions for routines in a project.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session
        status_filter: Optional filter by status
        date_filter: Optional filter by scheduled date (enforced by API layer for permission)
        start_date: Optional start date for date range filtering (inclusive)
        end_date: Optional end date for date range filtering (inclusive)
        routine_id: Optional filter by specific routine
        timezone: IANA timezone string for correct date filtering (e.g., 'America/Los_Angeles')
        include_details: If True, includes full submission details with responses

    Returns:
        ListExecutionsResponse with executions and total count
    """
    return await _implementation.list_executions(
        project_id,
        context,
        session,
        status_filter,
        date_filter,
        start_date,
        end_date,
        routine_id,
        timezone,
        include_details,
    )


async def update_execution_status(
    execution_id: UUID,
    new_status: ExecutionStatus,
    context: UserContext,
    session: AsyncSession,
) -> ExecutionDetailResponse:
    """
    Update the status of an execution.

    Args:
        execution_id: UUID of the execution
        new_status: New status value
        context: User authentication context
        session: Database session

    Returns:
        Updated ExecutionDetailResponse object
    """
    return await _implementation.update_execution_status(
        execution_id, new_status, context, session
    )


# ============================================================================
# Internal API Functions (Called by Lambda/Scheduler)
# ============================================================================


async def discover_routines_needing_executions(
    generation_count: int,
    pending_threshold: int,
    session: AsyncSession,
) -> DiscoveryResponse:
    """
    Discovery endpoint for routine execution generation.

    Queries database for schedules with fewer than threshold future pending executions
    and publishes RoutineExecutionGenerationRequested events for each.

    Called by EventBridge Scheduler (daily at 6am UTC).

    Args:
        generation_count: Number of executions to generate
        pending_threshold: Minimum number of future pending executions required
        session: Async database session

    Returns:
        DiscoveryResponse with counts and schedule IDs
    """
    return await _implementation.discover_routines_needing_executions(
        generation_count, pending_threshold, session
    )


async def generate_executions(
    request: GenerateExecutionsRequest,
    session: AsyncSession,
) -> GenerateExecutionsResponse:
    """
    Generate execution records for a schedule.

    Creates execution records using the schedule's configuration and
    calculate_next_executions utility.

    Called by Lambda function consuming RoutineExecutionGenerationRequested events.

    Args:
        request: Generation request with schedule_id and count
        session: Async database session

    Returns:
        GenerateExecutionsResponse with created execution IDs and date range
    """
    return await _implementation.generate_executions(request, session)


async def delete_future_executions(
    schedule_id: uuid.UUID,
    status_filter: ExecutionStatus,
    future_only: bool,
    session: AsyncSession,
) -> DeleteExecutionsResponse:
    """
    Delete future pending executions for a schedule.

    Used when a schedule is updated and executions need to be regenerated.
    Preserves completed and in_progress executions by default.

    Called by Lambda function after RoutineScheduleUpdated event with requires_regeneration=true.

    Args:
        schedule_id: UUID of the schedule
        status_filter: Status of executions to delete
        future_only: Only delete executions with scheduled_start > NOW()
        session: Async database session

    Returns:
        DeleteExecutionsResponse with count and IDs of deleted executions
    """
    return await _implementation.delete_future_executions(
        schedule_id, status_filter, future_only, session
    )
