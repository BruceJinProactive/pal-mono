"""Internal API endpoints for routine execution scheduling.

Called by Lambda functions and EventBridge Scheduler to manage routine execution lifecycle.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.operations.routine import (
    DeleteExecutionsResponse,
    DiscoveryResponse,
    GenerateExecutionsRequest,
    GenerateExecutionsResponse,
)
from db.tables.types import ExecutionStatus
from services import routine_execution_service
from utils.log import logger

routines_router = APIRouter(prefix="/routines")


@routines_router.post("/discovery", response_model=DiscoveryResponse)
async def discover_routines_needing_executions(
    generation_window_days: int = Query(
        30, ge=1, le=90, description="Days of executions to generate"
    ),
    pending_threshold: int = Query(
        7, ge=1, le=30, description="Minimum future pending executions required"
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> DiscoveryResponse:
    """
    Discovery endpoint for routine execution generation.

    Queries database for schedules with fewer than threshold future pending executions
    and publishes RoutineExecutionGenerationRequested events for each.

    Called daily by EventBridge Scheduler (6am UTC).

    Args:
        generation_window_days: Number of days to generate executions for
        pending_threshold: Minimum number of future pending executions required
        session: Async database session

    Returns:
        DiscoveryResponse with counts and schedule IDs
    """
    try:
        return await routine_execution_service.discover_routines_needing_executions(
            generation_window_days, pending_threshold, session
        )
    except Exception as e:
        logger.error(
            "[RoutineScheduler] Error in execution discovery",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover routines: {str(e)}",
            headers={"Content-Type": "application/json"},
        ) from e


@routines_router.post("/executions/generate", response_model=GenerateExecutionsResponse)
async def generate_executions(
    request: GenerateExecutionsRequest,
    session: AsyncSession = Depends(db.get_db_async),
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
    try:
        return await routine_execution_service.generate_executions(request, session)
    except ValueError as e:
        logger.warning(
            f"[RoutineScheduler] Validation error: {e}",
            extra={"schedule_id": str(request.schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        ) from e
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            "[RoutineScheduler] Database error generating executions",
            exc_info=True,
            extra={"schedule_id": str(request.schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate executions: {str(e)}",
            headers={"Content-Type": "application/json"},
        ) from e
    except Exception as e:
        await session.rollback()
        logger.error(
            "[RoutineScheduler] Error generating executions",
            exc_info=True,
            extra={"schedule_id": str(request.schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate executions: {str(e)}",
            headers={"Content-Type": "application/json"},
        ) from e


@routines_router.delete(
    "/schedules/{schedule_id}/executions", response_model=DeleteExecutionsResponse
)
async def delete_future_executions(
    schedule_id: uuid.UUID,
    status_filter: ExecutionStatus = Query(
        ExecutionStatus.pending,
        description="Status of executions to delete (default: pending)",
        alias="status",
    ),
    future_only: bool = Query(
        True, description="Only delete future executions (scheduled_start > NOW())"
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> DeleteExecutionsResponse:
    """
    Delete future pending executions for a schedule.

    Used when a schedule is updated and executions need to be regenerated.
    Preserves completed and in_progress executions by default.

    Called by Lambda function after RoutineScheduleUpdated event with requires_regeneration=true.

    Args:
        schedule_id: UUID of the schedule
        status_filter: Status of executions to delete (default: pending)
        future_only: Only delete executions with scheduled_start > NOW()
        session: Async database session

    Returns:
        DeleteExecutionsResponse with count and IDs of deleted executions
    """
    try:
        return await routine_execution_service.delete_future_executions(
            schedule_id, status_filter, future_only, session
        )
    except ValueError as e:
        logger.warning(
            f"[RoutineScheduler] Schedule not found: {e}",
            extra={"schedule_id": str(schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        ) from e
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(
            "[RoutineScheduler] Database error deleting executions",
            exc_info=True,
            extra={"schedule_id": str(schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete executions: {str(e)}",
            headers={"Content-Type": "application/json"},
        ) from e
    except Exception as e:
        await session.rollback()
        logger.error(
            "[RoutineScheduler] Error deleting executions",
            exc_info=True,
            extra={"schedule_id": str(schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete executions: {str(e)}",
            headers={"Content-Type": "application/json"},
        ) from e
