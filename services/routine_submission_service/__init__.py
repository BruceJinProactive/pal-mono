"""
Routine Submission Service

This service contains business logic for routine submission operations.
Handles staff workflow (start, add response, submit) and
manager workflow (list pending, approve, reject).
Authorization is handled in the API layer.
"""

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.routine import (
    ItemResponseWithItemResponse,
    ListPendingReviewResponse,
    RejectSubmissionRequest,
    SubmissionDetailResponse,
    SubmissionResponse,
)
from services.auth_types import UserContext

from . import _implementation

__all__ = [
    # Staff workflow
    "start_submission",
    "add_response",
    "submit_for_review",
    "get_submission",
    # Manager workflow
    "list_pending_review",
    "approve_submission",
    "reject_submission",
    # AI processing
    "process_response_ai",
]


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

    Args:
        execution_id: UUID of the execution
        context: User authentication context
        session: Database session

    Returns:
        Created SubmissionDetailResponse object
    """
    return await _implementation.start_submission(execution_id, context, session)


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

    Args:
        submission_id: UUID of the submission
        routine_item_id: UUID of the routine item
        file: Optional uploaded image file
        notes: Optional staff notes
        context: User authentication context
        session: Database session

    Returns:
        Created/updated ItemResponseWithItemResponse object
    """
    return await _implementation.add_response(
        submission_id, routine_item_id, file, notes, context, session
    )


async def submit_for_review(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Submit a draft submission for manager review.

    Args:
        submission_id: UUID of the submission
        context: User authentication context
        session: Database session

    Returns:
        Updated SubmissionResponse object
    """
    return await _implementation.submit_for_review(submission_id, context, session)


async def get_submission(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionDetailResponse:
    """
    Get a submission with its responses.

    Args:
        submission_id: UUID of the submission
        context: User authentication context
        session: Database session

    Returns:
        SubmissionDetailResponse object
    """
    return await _implementation.get_submission(submission_id, context, session)


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

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session

    Returns:
        ListPendingReviewResponse with submissions and total count
    """
    return await _implementation.list_pending_review(project_id, context, session)


async def approve_submission(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Approve a submitted submission.

    Args:
        submission_id: UUID of the submission
        context: User authentication context
        session: Database session

    Returns:
        Updated SubmissionResponse object
    """
    return await _implementation.approve_submission(submission_id, context, session)


async def reject_submission(
    submission_id: UUID,
    request: RejectSubmissionRequest,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Reject a submitted submission with notes.

    Args:
        submission_id: UUID of the submission
        request: Request containing rejection reason
        context: User authentication context
        session: Database session

    Returns:
        Updated SubmissionResponse object
    """
    return await _implementation.reject_submission(
        submission_id, request, context, session
    )


# ============================================================================
# AI Processing
# ============================================================================


async def process_response_ai(
    response_id: UUID,
    session: AsyncSession,
) -> None:
    """
    Process AI verification for an item response.

    TODO: Implement full AI vision integration.
    Currently stubbed - updates response with placeholder AI result.

    Args:
        response_id: UUID of the item response
        session: Database session
    """
    await _implementation.process_response_ai(response_id, session)
