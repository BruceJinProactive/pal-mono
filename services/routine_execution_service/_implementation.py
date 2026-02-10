"""
Routine Execution Service Implementation

Business logic for routine execution operations.
Authorization is handled in the API layer.
"""

import asyncio
import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    DeleteExecutionsResponse,
    DiscoveryResponse,
    ExecutionDetailResponse,
    GenerateExecutionsRequest,
    GenerateExecutionsResponse,
    ListExecutionsResponse,
    RoutineDetailResponse,
    SubmissionDetailResponse,
)
from db.repositories import (
    RoutineExecutionRepositoryAsync,
    RoutineRepositoryAsync,
    RoutineScheduleRepositoryAsync,
    RoutineSubmissionRepositoryAsync,
)
from db.tables.routine_executions import RoutineExecution
from db.tables.types import ExecutionStatus, RoutineCategory, SubmissionStatus
from events import RoutineExecutionGenerationRequested, publish_event
from services.auth_types import UserContext
from utils.log import logger


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
    start_date: date | None = None,
    end_date: date | None = None,
    routine_id: UUID | None = None,
    timezone: str | None = None,
    include_details: bool = False,
) -> ListExecutionsResponse:
    """
    List executions for routines in a project.

    Authorization is handled in the API layer, including date filtering
    for users without history access.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Async database session
        status_filter: Optional filter by execution status
        date_filter: Optional filter by date (pre-enforced by API layer for permissions) - single date
        start_date: Optional start date for date range filtering (inclusive)
        end_date: Optional end date for date range filtering (inclusive)
        routine_id: Optional filter by routine
        timezone: IANA timezone string for correct date filtering (e.g., 'America/Los_Angeles')
        include_details: If True, includes full submission details with responses
    """
    execution_repo = RoutineExecutionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    # Get executions (repository handles project_id filtering via JOIN)
    executions = await execution_repo.list_executions_by_project(
        project_id=project_id,
        status=status_filter,
        scheduled_date=date_filter,
        start_date=start_date,
        end_date=end_date,
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

        # Build submission detail if requested and submission exists
        submission_detail = None
        if include_details and submission:
            from services.routine_submission_service._implementation import (
                _build_item_response_batch,
            )

            # Extract all submission attributes immediately to prevent greenlet issues
            submission_data = {
                "id": submission.id,
                "execution_id": submission.execution_id,
                "status": submission.status,
                "submitted_by": submission.submitted_by,
                "submitted_at": submission.submitted_at,
                "reviewed_by": submission.reviewed_by,
                "reviewed_at": submission.reviewed_at,
                "review_notes": submission.review_notes,
                "created_at": submission.created_at,
                "updated_at": submission.updated_at,
            }

            responses = responses_by_submission.get(submission_data["id"], [])
            if responses:
                # Build item lookup for enriching responses
                routine_items = items_by_routine.get(execution.routine_id, [])
                item_map = {item.id: item for item in routine_items}

                # Build responses with batch presigned URL generation (parallelized S3 calls)
                response_list = await _build_item_response_batch(responses, item_map)

                # Fetch user names in parallel
                from services.routine_submission_service._implementation import (
                    _get_user_name_by_id,
                )

                submitted_by_name, reviewed_by_name = await asyncio.gather(
                    _get_user_name_by_id(session, submission_data["submitted_by"]),
                    _get_user_name_by_id(session, submission_data["reviewed_by"]),
                )

                # Build submission detail using extracted data
                submission_detail = SubmissionDetailResponse(
                    id=submission_data["id"],
                    execution_id=submission_data["execution_id"],
                    status=submission_data["status"],
                    submitted_by=submission_data["submitted_by"],
                    submitted_by_name=submitted_by_name,
                    submitted_at=submission_data["submitted_at"],
                    reviewed_by=submission_data["reviewed_by"],
                    reviewed_by_name=reviewed_by_name,
                    reviewed_at=submission_data["reviewed_at"],
                    review_notes=submission_data["review_notes"],
                    created_at=submission_data["created_at"],
                    updated_at=submission_data["updated_at"],
                    responses=response_list,
                    routine_name=routine_name,
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
                routine_detail=None,
                submission_detail=submission_detail,
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

    Raises:
        Exception: For any database or event publishing errors
    """
    logger.info(
        "[RoutineScheduler] Starting execution discovery",
        extra={
            "generation_count": generation_count,
            "pending_threshold": pending_threshold,
        },
    )

    # Query schedules with future pending execution count < threshold
    # Only count executions with scheduled_start > NOW()
    now_utc = datetime.now(timezone.utc)

    schedule_repo = RoutineScheduleRepositoryAsync(session)
    schedules_needing_replenishment = (
        await schedule_repo.find_schedules_needing_executions(
            pending_threshold=pending_threshold,
            now_utc=now_utc,
        )
    )

    logger.info(
        f"[RoutineScheduler] Found {len(schedules_needing_replenishment)} schedules needing replenishment",
        extra={"count": len(schedules_needing_replenishment)},
    )

    # Publish events for each schedule
    events_published = 0
    schedule_ids: list[uuid.UUID] = []
    errors = []

    for row in schedules_needing_replenishment:
        schedule_id = row["schedule_id"]
        routine_id = row["routine_id"]
        project_id = row["project_id"]
        future_pending_count = row["future_pending_count"]

        try:
            # For now, use project_id as account_id placeholder
            # TODO: Fetch actual account_id from project table
            account_id = project_id

            # Get last execution date for context
            execution_repo = RoutineExecutionRepositoryAsync(session)
            last_execution_date = await execution_repo.get_last_execution_date(
                schedule_id
            )

            # Publish event
            event = RoutineExecutionGenerationRequested(
                routine_id=routine_id,
                schedule_id=schedule_id,
                project_id=project_id,
                account_id=account_id,
                generation_count=generation_count,
                last_execution_date=(
                    last_execution_date.isoformat() if last_execution_date else None
                ),
                requested_at=datetime.now(timezone.utc),
                requested_by="scheduler",
            )

            success = await publish_event(event)

            if success:
                events_published += 1
                schedule_ids.append(schedule_id)
                logger.info(
                    f"[RoutineScheduler] Published generation event for schedule {schedule_id}",
                    extra={
                        "schedule_id": str(schedule_id),
                        "routine_id": str(routine_id),
                        "future_pending_count": future_pending_count,
                    },
                )
            else:
                error_msg = f"Failed to publish event for schedule {schedule_id}"
                errors.append(error_msg)
                logger.error(f"[RoutineScheduler] {error_msg}")

        except Exception as e:
            error_msg = f"Error processing schedule {schedule_id}: {str(e)}"
            errors.append(error_msg)
            logger.error(
                f"[RoutineScheduler] {error_msg}",
                exc_info=True,
                extra={"schedule_id": str(schedule_id)},
            )

    logger.info(
        f"[RoutineScheduler] Discovery complete: {events_published}/{len(schedules_needing_replenishment)} events published",
        extra={
            "schedules_found": len(schedules_needing_replenishment),
            "events_published": events_published,
            "errors_count": len(errors),
        },
    )

    return DiscoveryResponse(
        schedules_found=len(schedules_needing_replenishment),
        events_published=events_published,
        schedule_ids=schedule_ids,
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

    Raises:
        HTTPException: If schedule not found (404) or database error (500)
    """
    from services.routine_service import _schedule_calculator

    logger.info(
        f"[RoutineScheduler] Generating {request.count} executions for schedule {request.schedule_id}",
        extra={
            "schedule_id": str(request.schedule_id),
            "count": request.count,
            "from_date": str(request.from_date) if request.from_date else None,
        },
    )

    # Get schedule
    schedule_repo = RoutineScheduleRepositoryAsync(session)
    schedule = await schedule_repo.get_schedule_by_id(request.schedule_id)

    if not schedule:
        logger.warning(
            f"[RoutineScheduler] Schedule {request.schedule_id} not found",
            extra={"schedule_id": str(request.schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {request.schedule_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Calculate execution times
    from_date_to_use = request.from_date or date.today()

    execution_windows = _schedule_calculator.calculate_next_executions(
        frequency=schedule.frequency.value,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        timezone=schedule.timezone,
        days_of_week=schedule.days_of_week,
        day_of_month=schedule.day_of_month,
        effective_from=schedule.effective_from,
        effective_until=schedule.effective_until,
        count=request.count,
        from_date=from_date_to_use,
    )

    logger.info(
        f"[RoutineScheduler] Calculated {len(execution_windows)} execution windows",
        extra={
            "schedule_id": str(request.schedule_id),
            "windows_count": len(execution_windows),
        },
    )

    # Create execution records
    execution_repo = RoutineExecutionRepositoryAsync(session)
    created_executions: list[uuid.UUID] = []
    first_date: date | None = None
    last_date: date | None = None

    for scheduled_start, scheduled_end in execution_windows:
        execution = await execution_repo.create_execution(
            routine_id=schedule.routine_id,
            schedule_id=schedule.id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            status=ExecutionStatus.pending,
        )
        created_executions.append(execution.id)

        # Track date range
        execution_date = scheduled_start.date()
        if first_date is None or execution_date < first_date:
            first_date = execution_date
        if last_date is None or execution_date > last_date:
            last_date = execution_date

    await session.commit()

    logger.info(
        f"[RoutineScheduler] Created {len(created_executions)} executions for schedule {request.schedule_id}",
        extra={
            "schedule_id": str(request.schedule_id),
            "executions_created": len(created_executions),
            "first_date": str(first_date) if first_date else None,
            "last_date": str(last_date) if last_date else None,
        },
    )

    return GenerateExecutionsResponse(
        schedule_id=request.schedule_id,
        executions_created=len(created_executions),
        execution_ids=created_executions,
        date_range={
            "first_date": first_date,
            "last_date": last_date,
        },
    )


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

    Raises:
        HTTPException: If schedule not found (404) or database error (500)
    """
    logger.info(
        f"[RoutineScheduler] Deleting future {status_filter.value} executions for schedule {schedule_id}",
        extra={
            "schedule_id": str(schedule_id),
            "status_filter": status_filter.value,
            "future_only": future_only,
        },
    )

    # Get schedule to verify it exists
    schedule_repo = RoutineScheduleRepositoryAsync(session)
    schedule = await schedule_repo.get_schedule_by_id(schedule_id)

    if not schedule:
        logger.warning(
            f"[RoutineScheduler] Schedule {schedule_id} not found",
            extra={"schedule_id": str(schedule_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Find executions to delete
    now_utc = datetime.now(timezone.utc)

    execution_repo = RoutineExecutionRepositoryAsync(session)
    executions_to_delete = await execution_repo.find_executions_for_deletion(
        schedule_id=schedule_id,
        status_filter=status_filter,
        future_only=future_only,
        now_utc=now_utc,
    )

    logger.info(
        f"[RoutineScheduler] Found {len(executions_to_delete)} executions to delete",
        extra={
            "schedule_id": str(schedule_id),
            "count": len(executions_to_delete),
        },
    )

    # Delete executions and collect IDs
    deleted_ids: list[uuid.UUID] = []
    for execution in executions_to_delete:
        deleted_ids.append(execution.id)
        await session.delete(execution)

    await session.commit()

    logger.info(
        f"[RoutineScheduler] Deleted {len(deleted_ids)} executions for schedule {schedule_id}",
        extra={
            "schedule_id": str(schedule_id),
            "executions_deleted": len(deleted_ids),
        },
    )

    return DeleteExecutionsResponse(
        schedule_id=schedule_id,
        executions_deleted=len(deleted_ids),
        execution_ids=deleted_ids,
    )
