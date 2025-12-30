"""
Routine Execution Service Implementation

Business logic for routine execution operations.
Authorization is handled in the API layer.
"""

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    ExecutionDetailResponse,
    ListExecutionsResponse,
)
from db.repositories import (
    RoutineExecutionRepositoryAsync,
    RoutineRepositoryAsync,
    RoutineSubmissionRepositoryAsync,
)
from db.tables.routine_executions import RoutineExecution
from db.tables.types import ExecutionStatus
from services.auth_types import UserContext


def _build_execution_response(
    execution: RoutineExecution,
    routine_name: str | None = None,
    has_submission: bool = False,
) -> ExecutionDetailResponse:
    """Build an ExecutionDetailResponse from database model."""
    return ExecutionDetailResponse(
        id=execution.id,
        routine_id=execution.routine_id,
        schedule_id=execution.schedule_id,
        scheduled_start=execution.scheduled_start,
        scheduled_end=execution.scheduled_end,
        status=execution.status,
        assigned_user_id=execution.assigned_user_id,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
        routine_name=routine_name,
        has_submission=has_submission,
    )


async def get_execution(
    execution_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ExecutionDetailResponse:
    """
    Get an execution by ID.
    Authorization is handled in the API layer.
    """
    execution_repo = RoutineExecutionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    execution = await execution_repo.get_execution_by_id(execution_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Get routine name
    routine = await routine_repo.get_routine_by_id(execution.routine_id)
    routine_name = routine.name if routine else None

    # Check if has submission
    submission = await submission_repo.get_submission_by_execution_id(execution_id)
    has_submission = submission is not None

    return _build_execution_response(execution, routine_name, has_submission)


async def list_executions(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
    status_filter: ExecutionStatus | None = None,
    date_filter: date | None = None,
    routine_id: UUID | None = None,
) -> ListExecutionsResponse:
    """
    List executions for routines in a project.
    Authorization is handled in the API layer.
    """
    execution_repo = RoutineExecutionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    # Get executions (repository handles project_id filtering via JOIN)
    executions = await execution_repo.list_executions_by_project(
        project_id=project_id,
        status=status_filter,
        scheduled_date=date_filter,
        routine_id=routine_id,
    )

    if not executions:
        return ListExecutionsResponse(executions=[], total=0)

    # Get routines for name lookup
    routines = await routine_repo.list_routines_by_project(project_id)
    routine_names = {r.id: r.name for r in routines}

    # Get submissions for these executions
    execution_ids = [e.id for e in executions]
    submissions = await submission_repo.list_submissions_by_execution_ids(execution_ids)
    execution_has_submission = {s.execution_id for s in submissions}

    # Build responses
    responses = [
        _build_execution_response(
            execution=e,
            routine_name=routine_names.get(e.routine_id),
            has_submission=e.id in execution_has_submission,
        )
        for e in executions
    ]

    return ListExecutionsResponse(
        executions=responses,
        total=len(responses),
    )


async def update_execution_status(
    execution_id: UUID,
    new_status: ExecutionStatus,
    context: UserContext,
    session: AsyncSession,
) -> ExecutionDetailResponse:
    """
    Update the status of an execution.
    Authorization is handled in the API layer.
    """
    execution_repo = RoutineExecutionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    execution = await execution_repo.get_execution_by_id(execution_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
            headers={"Content-Type": "application/json"},
        )

    updated = await execution_repo.update_execution_status(
        execution_id=execution_id,
        status=new_status,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update execution {execution_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()

    # Get routine name
    routine = await routine_repo.get_routine_by_id(updated.routine_id)
    routine_name = routine.name if routine else None

    # Check if has submission
    submission = await submission_repo.get_submission_by_execution_id(execution_id)
    has_submission = submission is not None

    return _build_execution_response(updated, routine_name, has_submission)
