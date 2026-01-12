"""
Routine Submission Service Implementation

Business logic for routine submission operations.
Handles staff workflow and manager workflow.
Authorization is handled in the API layer.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    ItemResponseWithItemResponse,
    ListPendingReviewResponse,
    RejectSubmissionRequest,
    SubmissionDetailResponse,
    SubmissionResponse,
)
from db.repositories import (
    RoutineExecutionRepositoryAsync,
    RoutineRepositoryAsync,
    RoutineSubmissionRepositoryAsync,
)
from db.tables.routine_item_responses import RoutineItemResponse
from db.tables.routine_submissions import RoutineSubmission
from db.tables.types import ExecutionStatus, ItemResponseStatus, SubmissionStatus
from services.auth_types import UserContext


def _build_submission_response(submission: RoutineSubmission) -> SubmissionResponse:
    """Build a SubmissionResponse from database model."""
    return SubmissionResponse(
        id=submission.id,
        execution_id=submission.execution_id,
        status=submission.status,
        submitted_by=submission.submitted_by,
        submitted_at=submission.submitted_at,
        reviewed_by=submission.reviewed_by,
        reviewed_at=submission.reviewed_at,
        review_notes=submission.review_notes,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


def _build_item_response(
    response: RoutineItemResponse,
    item_name: str | None = None,
    item_description: str | None = None,
    is_required: bool = True,
) -> ItemResponseWithItemResponse:
    """Build an ItemResponseWithItemResponse from database model."""
    from services.asset_service import map_uri_to_s3_url

    # Convert S3 key to presigned URL at API boundary
    image_url = map_uri_to_s3_url(response.image_url) if response.image_url else None

    return ItemResponseWithItemResponse(
        id=response.id,
        submission_id=response.submission_id,
        routine_item_id=response.routine_item_id,
        image_url=image_url,  # Presigned URL for API response
        notes=response.notes,
        ai_result=response.ai_result,
        ai_passed=response.ai_passed,
        ai_confidence=response.ai_confidence,
        status=response.status,
        created_at=response.created_at,
        updated_at=response.updated_at,
        item_name=item_name,
        item_description=item_description,
        is_required=is_required,
    )


def _build_submission_detail_response(
    submission: RoutineSubmission,
    responses: list[ItemResponseWithItemResponse],
    routine_name: str | None = None,
) -> SubmissionDetailResponse:
    """Build a SubmissionDetailResponse from database models."""
    return SubmissionDetailResponse(
        id=submission.id,
        execution_id=submission.execution_id,
        status=submission.status,
        submitted_by=submission.submitted_by,
        submitted_at=submission.submitted_at,
        reviewed_by=submission.reviewed_by,
        reviewed_at=submission.reviewed_at,
        review_notes=submission.review_notes,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
        responses=responses,
        routine_name=routine_name,
    )


# ============================================================================
# Staff Workflow
# ============================================================================


async def start_submission(
    execution_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionDetailResponse:
    """
    Start a submission for an execution (creates draft).
    Authorization is handled in the API layer.
    """
    execution_repo = RoutineExecutionRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)

    # Check if execution exists
    execution = await execution_repo.get_execution_by_id(execution_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Check if submission already exists
    existing = await submission_repo.get_submission_by_execution_id(execution_id)

    if existing:
        # Return existing submission if already started
        return await get_submission(existing.id, context, session)

    # Get user ID from context
    user_id = None
    try:
        user_id = UUID(context.username)
    except (ValueError, TypeError):
        pass

    # Create the draft submission
    submission = await submission_repo.create_submission(
        execution_id=execution_id,
        status=SubmissionStatus.draft,
        submitted_by=user_id,
    )

    # Update execution status to in_progress
    await execution_repo.update_execution_status(
        execution_id=execution_id,
        status=ExecutionStatus.in_progress,
    )

    await session.commit()

    # Get routine name and items for response
    routine = await routine_repo.get_routine_by_id(execution.routine_id)
    routine_name = routine.name if routine else None

    # Return empty responses list (items haven't been responded to yet)
    return _build_submission_detail_response(
        submission=submission,
        responses=[],
        routine_name=routine_name,
    )


async def add_response(
    submission_id: UUID,
    routine_item_id: UUID,
    file: UploadFile | None,
    notes: str | None,
    context: UserContext,
    session: AsyncSession,
) -> ItemResponseWithItemResponse:
    """
    Add a response to a submission item.
    Authorization is handled in the API layer.
    """
    from services import asset_service

    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)

    # Get submission
    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Check submission is in draft status
    if submission.status != SubmissionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add responses to a submitted submission",
            headers={"Content-Type": "application/json"},
        )

    # Get the routine item
    item = await routine_repo.get_routine_item_by_id(routine_item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {routine_item_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Get execution to get routine for asset path
    execution = await execution_repo.get_execution_by_id(submission.execution_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {submission.execution_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Upload image if provided
    image_url = None
    if file:
        routine = await routine_repo.get_routine_by_id(execution.routine_id)

        if not routine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Routine {execution.routine_id} not found",
                headers={"Content-Type": "application/json"},
            )

        content = await file.read()
        filename = file.filename or "response.jpg"

        # Path: routines/{project_id}/{routine_id}/responses/{execution_id}/{item_id}_{filename}
        asset_path = (
            f"routines/{routine.project_id}/{routine.id}/responses/"
            f"{execution.id}/{routine_item_id}_{filename}"
        )

        from api.schemas.asset.asset import WriteAssetRequest

        asset_request = WriteAssetRequest(
            name=asset_path,
            content=content,
            metadata={},
        )
        # Run sync S3 operation in thread pool to avoid blocking async event loop
        response_asset = await asyncio.to_thread(
            asset_service.write_asset, asset_request
        )
        # Store the S3 key instead of presigned URL
        image_url = response_asset.url

    # Create or update the response
    response = await submission_repo.upsert_item_response(
        submission_id=submission_id,
        routine_item_id=routine_item_id,
        image_url=image_url,  # Now stores S3 key, not presigned URL
        notes=notes,
        status=ItemResponseStatus.pending,
    )

    # Trigger AI processing (stubbed for now)
    if image_url and item.ai_rules:
        # TODO: Implement async AI processing
        # For now, call synchronously but it's stubbed
        await process_response_ai(response.id, session)

    await session.commit()

    return _build_item_response(
        response=response,
        item_name=item.name,
        item_description=item.description,
        is_required=item.is_required,
    )


async def submit_for_review(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Submit a draft submission for manager review.
    Authorization is handled in the API layer.
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)

    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    if submission.status != SubmissionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission is not in draft status (current: {submission.status})",
            headers={"Content-Type": "application/json"},
        )

    # Get user ID from context
    user_id = None
    try:
        user_id = UUID(context.username)
    except (ValueError, TypeError):
        pass

    # Update submission status
    updated = await submission_repo.update_submission(
        submission_id=submission_id,
        status=SubmissionStatus.submitted,
        submitted_by=user_id,
        submitted_at=datetime.now(timezone.utc),
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update submission {submission_id}",
            headers={"Content-Type": "application/json"},
        )

    # Update execution status to completed
    await execution_repo.update_execution_status(
        execution_id=submission.execution_id,
        status=ExecutionStatus.completed,
    )

    await session.commit()

    return _build_submission_response(updated)


async def get_submission(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionDetailResponse:
    """
    Get a submission with its responses.
    Authorization is handled in the API layer.
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)

    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Get execution to get routine
    execution = await execution_repo.get_execution_by_id(submission.execution_id)

    # Get routine name
    routine = None
    routine_name = None
    if execution:
        routine = await routine_repo.get_routine_by_id(execution.routine_id)
        routine_name = routine.name if routine else None

    # Get all routine items for this routine
    items = []
    item_lookup = {}
    if routine:
        items = await routine_repo.list_items_by_routine(routine.id)
        item_lookup = {item.id: item for item in items}

    # Get responses
    db_responses = await submission_repo.list_responses_by_submission(submission_id)

    responses = []
    for response in db_responses:
        item = item_lookup.get(response.routine_item_id)
        responses.append(
            _build_item_response(
                response=response,
                item_name=item.name if item else None,
                item_description=item.description if item else None,
                is_required=item.is_required if item else True,
            )
        )

    return _build_submission_detail_response(
        submission=submission,
        responses=responses,
        routine_name=routine_name,
    )


# ============================================================================
# Manager Workflow
# ============================================================================


async def list_pending_review(
    project_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> ListPendingReviewResponse:
    """
    List submissions pending manager review.
    Authorization is handled in the API layer.
    """
    routine_repo = RoutineRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    # Get all routines for the project
    routines = await routine_repo.list_routines_by_project(project_id)
    routine_ids = [r.id for r in routines]

    if not routine_ids:
        return ListPendingReviewResponse(submissions=[], total=0)

    # Get all executions for these routines
    executions = []
    for routine_id in routine_ids:
        routine_executions = await execution_repo.list_executions_by_routine(routine_id)
        executions.extend(routine_executions)

    execution_ids = [e.id for e in executions]
    execution_routine_ids = {e.id: e.routine_id for e in executions}

    # Build routine name lookup
    routine_names = {r.id: r.name for r in routines}

    # Get pending submissions
    pending_submissions = await submission_repo.list_pending_review_submissions(
        execution_ids
    )

    # Build responses with details
    submissions = []
    for submission in pending_submissions:
        routine_id = execution_routine_ids.get(submission.execution_id)
        routine_name = routine_names.get(routine_id) if routine_id else None

        # Get items for this routine
        items = []
        item_lookup = {}
        if routine_id:
            items = await routine_repo.list_items_by_routine(routine_id)
            item_lookup = {item.id: item for item in items}

        # Get responses
        db_responses = await submission_repo.list_responses_by_submission(submission.id)

        responses = []
        for response in db_responses:
            item = item_lookup.get(response.routine_item_id)
            responses.append(
                _build_item_response(
                    response=response,
                    item_name=item.name if item else None,
                    item_description=item.description if item else None,
                    is_required=item.is_required if item else True,
                )
            )

        submissions.append(
            _build_submission_detail_response(
                submission=submission,
                responses=responses,
                routine_name=routine_name,
            )
        )

    return ListPendingReviewResponse(
        submissions=submissions,
        total=len(submissions),
    )


async def approve_submission(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Approve a submitted submission.
    Authorization is handled in the API layer.
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    if submission.status != SubmissionStatus.submitted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission is not awaiting review (current: {submission.status})",
            headers={"Content-Type": "application/json"},
        )

    # Get user ID from context
    reviewer_id = None
    try:
        reviewer_id = UUID(context.username)
    except (ValueError, TypeError):
        pass

    updated = await submission_repo.update_submission(
        submission_id=submission_id,
        status=SubmissionStatus.approved,
        reviewed_by=reviewer_id,
        reviewed_at=datetime.now(timezone.utc),
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update submission {submission_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()

    return _build_submission_response(updated)


async def reject_submission(
    submission_id: UUID,
    request: RejectSubmissionRequest,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Reject a submitted submission with notes.
    Authorization is handled in the API layer.
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    if submission.status != SubmissionStatus.submitted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission is not awaiting review (current: {submission.status})",
            headers={"Content-Type": "application/json"},
        )

    # Get user ID from context
    reviewer_id = None
    try:
        reviewer_id = UUID(context.username)
    except (ValueError, TypeError):
        pass

    # Reject and set back to draft for resubmission
    updated = await submission_repo.update_submission(
        submission_id=submission_id,
        status=SubmissionStatus.rejected,
        reviewed_by=reviewer_id,
        reviewed_at=datetime.now(timezone.utc),
        review_notes=request.review_notes,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update submission {submission_id}",
            headers={"Content-Type": "application/json"},
        )

    await session.commit()

    return _build_submission_response(updated)


# ============================================================================
# AI Processing
# ============================================================================


async def process_response_ai(
    response_id: UUID,
    session: AsyncSession,
) -> None:
    """
    Process AI verification for an item response.

    Note: Does not commit - caller is responsible for transaction management.

    TODO: Implement full AI vision integration.
    Currently stubbed - updates response with placeholder AI result.
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)

    response = await submission_repo.get_item_response_by_id(response_id)

    if not response:
        return

    # Get the routine item to check AI rules
    item = await routine_repo.get_routine_item_by_id(response.routine_item_id)

    if not item or not item.ai_rules:
        return

    # TODO: Implement actual AI vision call
    # For now, return a stub result
    stub_result = {
        "analysis_type": "ai_vision",
        "result": "pass",
        "confidence": 0.95,
        "finding": "TODO: AI verification not yet implemented",
        "details": {
            "criteria_met": [],
            "criteria_not_met": [],
            "observations": "Placeholder result - AI integration pending",
        },
        "model": "stub",
        "processing_time_ms": 0,
    }

    await submission_repo.update_item_response(
        response_id=response_id,
        ai_result=stub_result,
        ai_passed=True,
        ai_confidence=Decimal("0.95"),
        status=ItemResponseStatus.passed,
    )
