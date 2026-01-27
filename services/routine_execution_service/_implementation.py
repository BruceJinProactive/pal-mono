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
    RoutineDetailResponse,
    SubmissionDetailResponse,
)
from db.repositories import (
    RoutineExecutionRepositoryAsync,
    RoutineRepositoryAsync,
    RoutineSubmissionRepositoryAsync,
)
from db.tables.routine_executions import RoutineExecution
from db.tables.types import ExecutionStatus, RoutineCategory, SubmissionStatus
from services.auth_types import UserContext


def _build_execution_response(
    execution: RoutineExecution,
    routine_name: str | None,
    routine_category: RoutineCategory | None,
    routine_item_count: int,
    submission_id: UUID | None,
    submission_status: SubmissionStatus | None,
    submission_completed_count: int,
    routine_detail: RoutineDetailResponse | None = None,
    submission_detail: SubmissionDetailResponse | None = None,
) -> ExecutionDetailResponse:
    """
    Build ExecutionDetailResponse from execution data.
    All SQLAlchemy attributes are accessed immediately to prevent greenlet issues.
    """
    # Extract all execution attributes immediately
    execution_id = execution.id
    execution_routine_id = execution.routine_id
    execution_schedule_id = execution.schedule_id
    execution_scheduled_start = execution.scheduled_start
    execution_scheduled_end = execution.scheduled_end
    execution_status = execution.status
    execution_assigned_user_id = execution.assigned_user_id
    execution_created_at = execution.created_at
    execution_updated_at = execution.updated_at

    return ExecutionDetailResponse(
        id=execution_id,
        routine_id=execution_routine_id,
        schedule_id=execution_schedule_id,
        scheduled_start=execution_scheduled_start,
        scheduled_end=execution_scheduled_end,
        status=execution_status,
        assigned_user_id=execution_assigned_user_id,
        created_at=execution_created_at,
        updated_at=execution_updated_at,
        routine_name=routine_name,
        routine_category=routine_category,
        routine_item_count=routine_item_count,
        has_submission=submission_status is not None,
        submission_id=submission_id,
        submission_status=submission_status,
        submission_completed_count=submission_completed_count,
        submission_total_count=routine_item_count,
        routine=routine_detail,
        submission=submission_detail,
    )


async def get_execution(
    execution_id: UUID,
    context: UserContext,
    session: AsyncSession,
    details: bool = False,
) -> ExecutionDetailResponse:
    """
    Get an execution by ID.
    Authorization is handled in the API layer.
    """
    from services.routine_service._implementation import _build_routine_detail_response
    from services.routine_submission_service._implementation import (
        _build_item_response,
        _build_submission_detail_response,
    )

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

    # Fetch all related data
    routine = await routine_repo.get_routine_by_id(execution.routine_id)
    routine_items = await routine_repo.list_items_by_routine(execution.routine_id)
    submission = await submission_repo.get_submission_by_execution_id(execution_id)

    # Extract data immediately to prevent greenlet issues
    routine_name = routine.name if routine else None
    routine_category = routine.category if routine else None
    routine_item_count = len(routine_items)
    submission_id = submission.id if submission else None
    submission_status = submission.status if submission else None

    # Calculate submission completion and fetch responses
    submission_completed_count = 0
    responses = []
    if submission:
        responses = await submission_repo.list_responses_by_submission(submission.id)
        submission_completed_count = len(responses)

    # Build detailed responses if requested
    routine_detail: RoutineDetailResponse | None = None
    submission_detail: SubmissionDetailResponse | None = None

    if details:
        # Build routine detail with items
        if routine:
            routine_detail = await _build_routine_detail_response(
                routine, routine_items
            )

        # Build submission detail with responses (reuse already-fetched responses)
        if submission and responses:
            # Build item lookup for enriching responses
            item_map = {item.id: item for item in routine_items}
            response_list = []
            for response in responses:
                item = item_map.get(response.routine_item_id)
                response_with_item = await _build_item_response(
                    response,
                    item_name=item.name if item else None,
                    item_description=item.description if item else None,
                    is_required=item.is_required if item else True,
                )
                response_list.append(response_with_item)
            submission_detail = await _build_submission_detail_response(
                submission, response_list, session, routine_name
            )

    return _build_execution_response(
        execution,
        routine_name,
        routine_category,
        routine_item_count,
        submission_id,
        submission_status,
        submission_completed_count,
        routine_detail,
        submission_detail,
    )


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

    Authorization is handled in the API layer.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Async database session
        status_filter: Optional filter by execution status
        date_filter: Optional filter by date
        routine_id: Optional filter by routine
        timezone: IANA timezone string for correct date filtering (e.g., 'America/Los_Angeles')
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
        timezone=timezone,
    )

    if not executions:
        return ListExecutionsResponse(executions=[], total=0)

    # Fetch all routines and build lookup
    routines = await routine_repo.list_routines_by_project(project_id)
    routine_map = {r.id: r for r in routines}

    # Fetch routine items in batch (single DB call)
    items_by_routine = await routine_repo.list_items_by_routine_ids(
        list(routine_map.keys())
    )
    routine_item_counts = {rid: len(items) for rid, items in items_by_routine.items()}

    # Fetch submissions in batch
    execution_ids = [e.id for e in executions]
    submissions = await submission_repo.list_submissions_by_execution_ids(execution_ids)
    submission_map = {s.execution_id: s for s in submissions}

    # Fetch item responses in batch (single DB call)
    submission_ids = [s.id for s in submissions]
    responses_by_submission = await submission_repo.list_responses_by_submission_ids(
        submission_ids
    )

    # Build response list
    result = []
    for execution in executions:
        # Extract all data immediately to prevent greenlet issues
        routine = routine_map.get(execution.routine_id)
        submission = submission_map.get(execution.id)

        routine_name = routine.name if routine else None
        routine_category = routine.category if routine else None
        routine_item_count = routine_item_counts.get(execution.routine_id, 0)
        submission_id = submission.id if submission else None
        submission_status = submission.status if submission else None
        submission_completed_count = (
            len(responses_by_submission.get(submission.id, [])) if submission else 0
        )

        result.append(
            _build_execution_response(
                execution,
                routine_name,
                routine_category,
                routine_item_count,
                submission_id,
                submission_status,
                submission_completed_count,
            )
        )

    return ListExecutionsResponse(executions=result, total=len(result))


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

    # Fetch all related data
    routine = await routine_repo.get_routine_by_id(updated.routine_id)
    routine_items = await routine_repo.list_items_by_routine(updated.routine_id)
    submission = await submission_repo.get_submission_by_execution_id(execution_id)

    # Extract data immediately to prevent greenlet issues
    routine_name = routine.name if routine else None
    routine_category = routine.category if routine else None
    routine_item_count = len(routine_items)
    submission_id = submission.id if submission else None
    submission_status = submission.status if submission else None

    # Calculate submission completion
    submission_completed_count = 0
    if submission:
        responses = await submission_repo.list_responses_by_submission(submission.id)
        submission_completed_count = len(responses)

    return _build_execution_response(
        updated,
        routine_name,
        routine_category,
        routine_item_count,
        submission_id,
        submission_status,
        submission_completed_count,
    )
