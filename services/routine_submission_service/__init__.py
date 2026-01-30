"""
Routine Submission Service

This service contains business logic for routine submission operations.
Handles staff workflow (start, add response, submit) and
manager workflow (list pending, approve, reject).
Includes AI-powered verification for routine items.
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

from . import _implementation, _llm

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
    "reset_to_draft",
    # AI processing
    "analyze_routine_item_response",
    "process_response_with_ai",
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


async def reset_to_draft(
    submission_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> SubmissionResponse:
    """
    Reset a submission back to draft status for resubmission.

    This allows resetting submissions from any status (submitted, approved, rejected)
    back to draft, enabling staff to modify responses and resubmit.

    Args:
        submission_id: UUID of the submission
        context: User authentication context
        session: Database session

    Returns:
        Updated SubmissionResponse object with draft status
    """
    return await _implementation.reset_to_draft(submission_id, context, session)


# ============================================================================
# AI Processing
# ============================================================================


async def analyze_routine_item_response(
    session: AsyncSession,
    response_id: UUID,
) -> dict:
    """
    Execute LLM analysis for a routine item response.

    Retrieves the routine item configuration, fetches reference images and submitted image,
    and performs AI analysis using Azure OpenAI or Google Gemini Vision API.

    Args:
        session: Database session
        response_id: UUID of the routine item response to analyze

    Returns:
        dict: Analysis result with keys:
            {
                "result": "pass" or "fail" or "error",
                "details": str,
                "confidence": float (0.0-1.0),
                "findings": list[str] (optional)
            }
    """
    return await _llm.analyze_routine_item_response(session, response_id)


async def process_response_with_ai(
    session: AsyncSession,
    response_id: UUID,
):
    """
    Process AI verification for a routine item response and update the database.

    This function runs LLM analysis on the submitted image and updates the response
    record with AI results (ai_result, ai_passed, ai_confidence, status).

    Note: Does not commit - caller is responsible for transaction management.

    Args:
        session: Database session
        response_id: UUID of the item response

    Returns:
        Updated RoutineItemResponse object with AI results
    """
    return await _llm.process_response_with_ai(session, response_id)
