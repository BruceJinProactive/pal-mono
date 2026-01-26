"""
Routine Operation Routes Implementation

This module handles authorization and delegates to routine services for business logic.
"""

from datetime import date
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    CreateRoutineItemRequest,
    CreateRoutineRequest,
    CreateScheduleRequest,
    ExecutionDetailResponse,
    ItemResponseWithItemResponse,
    ListExecutionsResponse,
    ListPendingReviewResponse,
    ListRoutinesResponse,
    ListSchedulesResponse,
    RejectSubmissionRequest,
    RoutineDetailResponse,
    RoutineItemResponse,
    RoutineResponse,
    ScheduleResponse,
    SubmissionDetailResponse,
    SubmissionResponse,
    UpdateReferenceImagesRequest,
    UpdateRoutineItemRequest,
    UpdateRoutineRequest,
    UpdateScheduleRequest,
)
from db.tables.types import ExecutionStatus
from services import (
    routine_execution_service,
    routine_schedule_service,
    routine_service,
    routine_submission_service,
)
from services.auth_types import UserContext

# ============================================================================
# Routine Management
# ============================================================================


async def create_routine(
    project_id: UUID,
    request: CreateRoutineRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineDetailResponse:
    """Create a new routine with optional items and schedule."""
    return await routine_service.create_routine(project_id, request, context, session)


async def list_routines(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
    is_active: bool | None = None,
) -> ListRoutinesResponse:
    """List routines for a project."""
    return await routine_service.list_routines(project_id, context, session, is_active)


async def get_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> RoutineDetailResponse:
    """Get a routine by ID with its items."""
    return await routine_service.get_routine(routine_id, context, session)


async def update_routine(
    routine_id: UUID,
    request: UpdateRoutineRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineResponse:
    """Update a routine."""
    return await routine_service.update_routine(routine_id, request, context, session)


async def delete_routine(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """Delete a routine."""
    await routine_service.delete_routine(routine_id, context, session)


# ============================================================================
# Routine Items
# ============================================================================


async def add_item(
    routine_id: UUID,
    request: CreateRoutineItemRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """Add an item to a routine."""
    return await routine_service.add_item(routine_id, request, context, session)


async def update_item(
    item_id: UUID,
    request: UpdateRoutineItemRequest,
    context: UserContext,
    session: AsyncSession,
) -> RoutineItemResponse:
    """Update a routine item."""
    return await routine_service.update_item(item_id, request, context, session)


async def delete_item(
    item_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """Delete a routine item."""
    await routine_service.delete_item(item_id, context, session)


async def upload_reference_image(
    item_id: UUID,
    file: UploadFile,
    description: str | None,
    context: UserContext,
    session: AsyncSession,
) -> dict[str, str]:
    """Upload a reference image for a routine item."""
    return await routine_service.upload_reference_image(
        item_id, file, description, context, session
    )


async def update_reference_images(
    item_id: UUID,
    request: UpdateReferenceImagesRequest,
    context: UserContext,
    session: AsyncSession,
) -> list[dict[str, str]]:
    """Update the complete list of reference images for a routine item."""
    # Convert Pydantic models to dicts
    new_images = [img.model_dump() for img in request.reference_images]
    return await routine_service.update_reference_images(
        item_id, new_images, context, session
    )


# ============================================================================
# Schedules
# ============================================================================


async def create_schedule(
    routine_id: UUID,
    request: CreateScheduleRequest,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """Create a schedule for a routine."""
    return await routine_schedule_service.create_schedule(
        routine_id, request, context, session
    )


async def list_schedules(
    routine_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ListSchedulesResponse:
    """List schedules for a routine."""
    return await routine_schedule_service.list_schedules(routine_id, context, session)


async def update_schedule(
    schedule_id: UUID,
    request: UpdateScheduleRequest,
    context: UserContext,
    session: AsyncSession,
) -> ScheduleResponse:
    """Update a schedule."""
    return await routine_schedule_service.update_schedule(
        schedule_id, request, context, session
    )


async def delete_schedule(
    schedule_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """Delete a schedule."""
    await routine_schedule_service.delete_schedule(schedule_id, context, session)


# ============================================================================
# Executions
# ============================================================================


async def list_executions(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
    status_filter: ExecutionStatus | None = None,
    date_filter: date | None = None,
    routine_id: UUID | None = None,
    timezone: str | None = None,
) -> ListExecutionsResponse:
    """List executions for routines in a project."""
    return await routine_execution_service.list_executions(
        project_id, context, session, status_filter, date_filter, routine_id, timezone
    )


async def get_execution(
    execution_id: UUID,
    context: UserContext,
    session: AsyncSession,
    details: bool = False,
) -> ExecutionDetailResponse:
    """Get an execution by ID."""
    return await routine_execution_service.get_execution(
        execution_id, context, session, details
    )


# ============================================================================
# Submissions - Staff Workflow
# ============================================================================


async def start_submission(
    execution_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionDetailResponse:
    """Start a submission for an execution (creates draft)."""
    return await routine_submission_service.start_submission(
        execution_id, context, session
    )


async def get_submission(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionDetailResponse:
    """Get a submission with its responses."""
    return await routine_submission_service.get_submission(
        submission_id, context, session
    )


async def add_response(
    submission_id: UUID,
    routine_item_id: UUID,
    file: UploadFile | None,
    notes: str | None,
    context: UserContext,
    session: AsyncSession,
) -> ItemResponseWithItemResponse:
    """Add a response to a submission item."""
    return await routine_submission_service.add_response(
        submission_id,
        routine_item_id,
        file,
        notes,
        context,
        session,
    )


async def submit_for_review(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """Submit a draft submission for manager review."""
    return await routine_submission_service.submit_for_review(
        submission_id, context, session
    )


# ============================================================================
# Submissions - Manager Workflow
# ============================================================================


async def list_pending_review(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ListPendingReviewResponse:
    """List submissions pending manager review."""
    return await routine_submission_service.list_pending_review(
        project_id, context, session
    )


async def approve_submission(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """Approve a submitted submission."""
    return await routine_submission_service.approve_submission(
        submission_id, context, session
    )


async def reject_submission(
    submission_id: UUID,
    request: RejectSubmissionRequest,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """Reject a submitted submission with notes."""
    return await routine_submission_service.reject_submission(
        submission_id, request, context, session
    )


async def reset_to_draft(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """Reset a submission back to draft status for resubmission."""
    return await routine_submission_service.reset_to_draft(
        submission_id, context, session
    )
