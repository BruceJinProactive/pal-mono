"""
Routine Execution Service

This service contains business logic for routine execution operations.
Authorization is handled in the API layer.
"""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    ExecutionDetailResponse,
    ListExecutionsResponse,
)
from db.tables.types import ExecutionStatus
from services.auth_types import UserContext

from . import _implementation

__all__ = [
    "get_execution",
    "list_executions",
    "update_execution_status",
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
    routine_id: UUID | None = None,
    timezone: str | None = None,
) -> ListExecutionsResponse:
    """
    List executions for routines in a project.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session
        status_filter: Optional filter by status
        date_filter: Optional filter by scheduled date (enforced by API layer for permission)
        routine_id: Optional filter by specific routine
        timezone: IANA timezone string for correct date filtering (e.g., 'America/Los_Angeles')

    Returns:
        ListExecutionsResponse with executions and total count
    """
    return await _implementation.list_executions(
        project_id, context, session, status_filter, date_filter, routine_id, timezone
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
