"""
Routine Submission Service Implementation

Business logic for routine submission operations.
Handles staff workflow and manager workflow.
Authorization is handled in the API layer.
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
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
from db.tables.account_user import AccountUser
from db.tables.routine_item_responses import RoutineItemResponse
from db.tables.routine_submissions import RoutineSubmission
from db.tables.types import ExecutionStatus, ItemResponseStatus, SubmissionStatus
from services.auth_types import UserContext
from utils.log import logger


async def _get_user_name_by_id(
    session: AsyncSession, user_id: UUID | None
) -> str | None:
    """Get user's full name from AccountUser table by user_id.

    Args:
        session: Async database session
        user_id: UUID of the user to look up

    Returns:
        User's full name if found, None otherwise
    """
    if not user_id:
        return None

    try:
        query = select(AccountUser).filter(AccountUser.user_id == user_id)
        result = await session.execute(query)
        account_user = result.scalars().first()
        return account_user.name if account_user else None
    except Exception as e:
        logger.error(f"Error fetching user name for user_id {user_id}: {e}")
        return None


async def _build_submission_response(
    submission: RoutineSubmission, session: AsyncSession
) -> SubmissionResponse:
    """Build a SubmissionResponse from database model.

    Args:
        submission: The submission database model
        session: Async database session for fetching user names

    Returns:
        SubmissionResponse with user names populated
    """
    # Fetch user names if user IDs are present
    submitted_by_name = await _get_user_name_by_id(session, submission.submitted_by)
    reviewed_by_name = await _get_user_name_by_id(session, submission.reviewed_by)

    return SubmissionResponse(
        id=submission.id,
        execution_id=submission.execution_id,
        status=submission.status,
        submitted_by=submission.submitted_by,
        submitted_by_name=submitted_by_name,
        submitted_at=submission.submitted_at,
        reviewed_by=submission.reviewed_by,
        reviewed_by_name=reviewed_by_name,
        reviewed_at=submission.reviewed_at,
        review_notes=submission.review_notes,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


async def _build_item_response(
    response: RoutineItemResponse,
    item_name: str | None = None,
    item_description: str | None = None,
    is_required: bool = True,
) -> ItemResponseWithItemResponse:
    """Build an ItemResponseWithItemResponse from database model."""
    from services.asset_service import map_uri_to_s3_url

    # Convert S3 key to presigned URL at API boundary (run in thread pool)
    if response.image_url:
        image_url = await asyncio.to_thread(map_uri_to_s3_url, response.image_url)
    else:
        image_url = None

    # Extract ai_details from ai_result JSON
    ai_details = None
    if response.ai_result and isinstance(response.ai_result, dict):
        ai_details = response.ai_result.get("details")

    return ItemResponseWithItemResponse(
        id=response.id,
        submission_id=response.submission_id,
        routine_item_id=response.routine_item_id,
        image_url=image_url,  # Presigned URL for API response
        notes=response.notes,
        ai_result=response.ai_result,
        ai_passed=response.ai_passed,
        ai_confidence=response.ai_confidence,
        ai_details=ai_details,
        status=response.status,
        created_at=response.created_at,
        updated_at=response.updated_at,
        item_name=item_name,
        item_description=item_description,
        is_required=is_required,
    )


async def _build_submission_detail_response(
    submission: RoutineSubmission,
    responses: list[ItemResponseWithItemResponse],
    session: AsyncSession,
    routine_name: str | None = None,
) -> SubmissionDetailResponse:
    """Build a SubmissionDetailResponse from database models.

    Args:
        submission: The submission database model
        responses: List of item responses with details
        session: Async database session for fetching user names
        routine_name: Optional routine name

    Returns:
        SubmissionDetailResponse with user names populated
    """
    # Fetch user names if user IDs are present
    submitted_by_name = await _get_user_name_by_id(session, submission.submitted_by)
    reviewed_by_name = await _get_user_name_by_id(session, submission.reviewed_by)

    return SubmissionDetailResponse(
        id=submission.id,
        execution_id=submission.execution_id,
        status=submission.status,
        submitted_by=submission.submitted_by,
        submitted_by_name=submitted_by_name,
        submitted_at=submission.submitted_at,
        reviewed_by=submission.reviewed_by,
        reviewed_by_name=reviewed_by_name,
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

    # Cache execution.routine_id before commit to avoid lazy-loading issues
    routine_id = execution.routine_id

    await session.commit()

    # Get routine name and items for response
    routine = await routine_repo.get_routine_by_id(routine_id)
    routine_name = routine.name if routine else None

    # Return empty responses list (items haven't been responded to yet)
    return await _build_submission_detail_response(
        submission=submission,
        responses=[],
        session=session,
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

    Args:
        submission_id: UUID of the submission
        routine_item_id: UUID of the routine item to respond to
        file: Optional image file
        notes: Optional notes
        context: User authentication context
        session: Async database session
    """
    logger.info(
        f"[add_response] Starting - submission_id={submission_id}, "
        f"routine_item_id={routine_item_id}, "
        f"has_file={file is not None}, has_notes={notes is not None}"
    )

    from services import asset_service

    submission_repo = RoutineSubmissionRepositoryAsync(session)
    routine_repo = RoutineRepositoryAsync(session)
    execution_repo = RoutineExecutionRepositoryAsync(session)

    # Get submission
    logger.debug(f"[add_response] Fetching submission: {submission_id}")
    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        logger.error(f"[add_response] Submission not found: {submission_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    logger.debug(
        f"[add_response] Submission found - status={submission.status}, "
        f"execution_id={submission.execution_id}"
    )

    # Check submission is in draft status
    if submission.status != SubmissionStatus.draft:
        logger.warning(
            f"[add_response] Cannot add response to non-draft submission: "
            f"submission_id={submission_id}, status={submission.status}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add responses to a submitted submission",
            headers={"Content-Type": "application/json"},
        )

    # Get the routine item
    logger.debug(f"[add_response] Fetching routine item: {routine_item_id}")
    item = await routine_repo.get_routine_item_by_id(routine_item_id)

    if not item:
        logger.error(f"[add_response] Routine item not found: {routine_item_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routine item {routine_item_id} not found",
            headers={"Content-Type": "application/json"},
        )

    logger.debug(
        f"[add_response] Routine item found - name={item.name}, "
        f"routine_id={item.routine_id}, has_ai_rules={item.ai_rules is not None}"
    )

    # Get execution to get routine for asset path
    logger.debug(f"[add_response] Fetching execution: {submission.execution_id}")
    execution = await execution_repo.get_execution_by_id(submission.execution_id)

    if not execution:
        logger.error(f"[add_response] Execution not found: {submission.execution_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {submission.execution_id} not found",
            headers={"Content-Type": "application/json"},
        )

    logger.debug(f"[add_response] Execution found - routine_id={execution.routine_id}")

    # Upload image if provided
    image_url = None
    if file:
        logger.info(
            f"[add_response] File upload requested - "
            f"filename={file.filename}, content_type={file.content_type}"
        )

        logger.debug(f"[add_response] Fetching routine: {execution.routine_id}")
        routine = await routine_repo.get_routine_by_id(execution.routine_id)

        if not routine:
            logger.error(f"[add_response] Routine not found: {execution.routine_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Routine {execution.routine_id} not found",
                headers={"Content-Type": "application/json"},
            )

        logger.debug("[add_response] Reading file content")
        content = await file.read()
        filename = file.filename or "response.jpg"

        logger.debug(f"[add_response] File size: {len(content)} bytes")

        # Path: routines/{project_id}/{routine_id}/responses/{execution_id}/{item_id}_{filename}
        asset_path = (
            f"routines/{routine.project_id}/{routine.id}/responses/"
            f"{execution.id}/{routine_item_id}_{filename}"
        )

        logger.info(f"[add_response] Uploading to S3 - path={asset_path}")

        from api.schemas.asset.asset import WriteAssetRequest

        asset_request = WriteAssetRequest(
            name=asset_path,
            content=content,
            metadata={},
        )

        try:
            # Run sync S3 operation in thread pool to avoid blocking async event loop
            response_asset = await asyncio.to_thread(
                asset_service.write_asset, asset_request
            )

            # Store the S3 key instead of presigned URL
            image_url = response_asset.url
            logger.info(f"[add_response] S3 upload successful - s3_key={image_url}")
        except Exception as e:
            logger.error(
                f"[add_response] S3 upload failed - "
                f"path={asset_path}, error={type(e).__name__}: {str(e)}"
            )
            raise

    # Create or update the response
    logger.debug(
        f"[add_response] Upserting item response - "
        f"submission_id={submission_id}, routine_item_id={routine_item_id}"
    )

    try:
        response = await submission_repo.upsert_item_response(
            submission_id=submission_id,
            routine_item_id=routine_item_id,
            image_url=image_url,  # Now stores S3 key, not presigned URL
            notes=notes,
            status=ItemResponseStatus.pending,
        )
        logger.debug(
            f"[add_response] Item response upserted - response_id={response.id}"
        )
    except Exception as e:
        logger.error(
            f"[add_response] Failed to upsert item response - "
            f"error={type(e).__name__}: {str(e)}"
        )
        raise

    # Trigger AI processing if image and AI rules are present
    if image_url and item.ai_rules:
        logger.info(
            f"[add_response] Triggering AI processing - "
            f"response_id={response.id}, ai_rules={item.ai_rules}"
        )
        try:
            from services.routine_submission_service._llm import (
                process_response_with_ai,
            )

            response = await process_response_with_ai(
                session=session,
                response_id=response.id,
            )
            logger.debug("[add_response] AI processing completed")
        except Exception as e:
            logger.error(
                f"[add_response] AI processing failed - "
                f"error={type(e).__name__}: {str(e)}"
            )
            # Don't raise - AI processing failure shouldn't block response creation

    # Access SQLAlchemy model attributes BEFORE commit to avoid lazy-loading issues
    logger.debug(
        "[add_response] Capturing response data BEFORE commit "
        "(prevents greenlet errors from lazy-loading)"
    )
    try:
        response_data = {
            "id": response.id,
            "submission_id": response.submission_id,
            "routine_item_id": response.routine_item_id,
            "image_url": response.image_url,  # Access before commit!
            "notes": response.notes,
            "ai_result": response.ai_result,
            "ai_passed": response.ai_passed,
            "ai_confidence": response.ai_confidence,
            "status": response.status,
            "created_at": response.created_at,
            "updated_at": response.updated_at,
        }
        logger.debug("[add_response] Response data captured successfully")
    except Exception as e:
        logger.error(
            f"[add_response] GREENLET ERROR: Failed to access SQLAlchemy attributes - "
            f"error={type(e).__name__}: {str(e)}, "
            f"This might be a lazy-loading issue!"
        )
        raise

    # Cache item attributes before commit to avoid lazy-loading issues
    item_name = item.name
    item_description = item.description
    item_is_required = item.is_required

    await session.commit()

    # Convert S3 key to presigned URL (run in thread pool)
    logger.debug("[add_response] Converting S3 key to presigned URL")
    from services.asset_service import map_uri_to_s3_url

    if response_data["image_url"]:
        try:
            logger.debug(
                f"[add_response] Calling map_uri_to_s3_url in thread pool - "
                f"s3_key={response_data['image_url']}"
            )
            presigned_url = await asyncio.to_thread(
                map_uri_to_s3_url, response_data["image_url"]
            )

            # Normalize empty string to None to match _build_item_response behavior
            if presigned_url == "":
                presigned_url = None

            logger.debug(
                f"[add_response] Presigned URL generated - "
                f"url_exists={presigned_url is not None}"
            )
        except Exception as e:
            logger.error(
                f"[add_response] GREENLET ERROR: Failed to generate presigned URL - "
                f"error={type(e).__name__}: {str(e)}, "
                f"s3_key={response_data['image_url']}"
            )
            raise
    else:
        presigned_url = None
        logger.debug("[add_response] No image URL to convert")

    # Extract ai_details from ai_result JSON
    ai_details = None
    if response_data["ai_result"] and isinstance(response_data["ai_result"], dict):
        ai_details = response_data["ai_result"].get("details")

    result = ItemResponseWithItemResponse(
        id=response_data["id"],
        submission_id=response_data["submission_id"],
        routine_item_id=response_data["routine_item_id"],
        image_url=presigned_url,  # Presigned URL for API response
        notes=response_data["notes"],
        ai_result=response_data["ai_result"],
        ai_passed=response_data["ai_passed"],
        ai_confidence=response_data["ai_confidence"],
        ai_details=ai_details,
        status=response_data["status"],
        created_at=response_data["created_at"],
        updated_at=response_data["updated_at"],
        item_name=item_name,
        item_description=item_description,
        is_required=item_is_required,
    )

    logger.info(
        f"[add_response] Completed successfully - "
        f"response_id={result.id}, has_image={result.image_url is not None}"
    )

    return result


async def submit_for_review(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Submit a draft submission for manager review.
    Authorization is handled in the API layer.

    Args:
        submission_id: UUID of the submission
        context: User authentication context
        session: Async database session
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

    # Get user ID from context
    try:
        user_id = UUID(context.username)
    except (ValueError, TypeError):
        user_id = None

    if submission.status != SubmissionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission is not in draft status (current: {submission.status})",
            headers={"Content-Type": "application/json"},
        )

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
        execution_id=updated.execution_id,
        status=ExecutionStatus.completed,
    )

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in async _build_submission_response would trigger greenlet errors)
    response = await _build_submission_response(updated, session)

    await session.commit()

    return response


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

    # Build responses concurrently using asyncio.gather
    response_tasks = []
    for response in db_responses:
        item = item_lookup.get(response.routine_item_id)
        response_tasks.append(
            _build_item_response(
                response=response,
                item_name=item.name if item else None,
                item_description=item.description if item else None,
                is_required=item.is_required if item else True,
            )
        )

    responses = await asyncio.gather(*response_tasks)

    return await _build_submission_detail_response(
        submission=submission,
        responses=responses,
        session=session,
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

        # Build responses concurrently using asyncio.gather
        response_tasks = []
        for response in db_responses:
            item = item_lookup.get(response.routine_item_id)
            response_tasks.append(
                _build_item_response(
                    response=response,
                    item_name=item.name if item else None,
                    item_description=item.description if item else None,
                    is_required=item.is_required if item else True,
                )
            )

        responses = await asyncio.gather(*response_tasks)

        submission_detail = await _build_submission_detail_response(
            submission=submission,
            responses=responses,
            session=session,
            routine_name=routine_name,
        )
        submissions.append(submission_detail)

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

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in async _build_submission_response would trigger greenlet errors)
    response = await _build_submission_response(updated, session)

    await session.commit()

    return response


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

    # Build response before commit to avoid async I/O issues
    # (session.commit() expires objects, and accessing attributes
    # in async _build_submission_response would trigger greenlet errors)
    response = await _build_submission_response(updated, session)

    await session.commit()

    return response


async def reset_to_draft(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Reset a submission back to draft status for resubmission.

    This allows staff to modify and resubmit submissions that were:
    - rejected (to fix issues)
    - submitted (to make changes before review)
    - approved (to make corrections if needed)

    When reset to draft:
    - Status changes to 'draft'
    - Review metadata (reviewed_by, reviewed_at, review_notes) is cleared
    - Submission metadata (submitted_by, submitted_at) is cleared
    - Item responses remain unchanged (staff can modify them)
    - Execution status remains 'completed' (routine was physically done)

    Authorization is handled in the API layer.

    Args:
        submission_id: UUID of the submission to reset
        context: User authentication context
        session: Database session

    Returns:
        Updated SubmissionResponse object with status='draft'

    Raises:
        HTTPException: If submission not found or already in draft status
    """
    submission_repo = RoutineSubmissionRepositoryAsync(session)

    submission = await submission_repo.get_submission_by_id(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {submission_id} not found",
            headers={"Content-Type": "application/json"},
        )

    if submission.status == SubmissionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission is already in draft status",
            headers={"Content-Type": "application/json"},
        )

    # Cache previous status before update to avoid lazy-loading issues
    previous_status = submission.status

    # Reset to draft: clear all review and submission metadata
    updated = await submission_repo.update_submission(
        submission_id=submission_id,
        status=SubmissionStatus.draft,
        submitted_by=None,
        submitted_at=None,
        reviewed_by=None,
        reviewed_at=None,
        review_notes=None,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset submission {submission_id}",
            headers={"Content-Type": "application/json"},
        )

    logger.info(
        f"[reset_to_draft] Submission reset to draft: "
        f"submission_id={submission_id}, "
        f"previous_status={previous_status}, "
        f"reset_by={context.username}"
    )

    # Build response before commit to avoid async I/O issues
    response = await _build_submission_response(updated, session)

    await session.commit()

    return response


# ============================================================================
# AI Processing
# ============================================================================
# Note: AI processing logic has been moved to _llm.py
# Import and use process_response_with_ai from that module
