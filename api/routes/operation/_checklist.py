"""
Checklist Operation Routes

This module delegates to the checklist_service for all business logic.
It only handles request/response formatting and passes through to the service layer.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.checklist import (
    Checklist,
    ChecklistCheckpointStatusResponse,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from services import checklist_service


async def create_checklist(
    project_id: UUID,
    checklist_request: CreateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Create a new checklist for a project.
    Delegates to checklist_service.
    """
    return await checklist_service.create_checklist(
        project_id, checklist_request, context, session
    )


async def get_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Get a checklist by ID.
    Delegates to checklist_service.
    """
    return await checklist_service.get_checklist(checklist_id, context, session)


async def list_checklists_by_project(
    project_id: UUID,
    context: UserContext,
    session: Session,
    exclude: UUID | None = None,
) -> ListChecklistsResponse:
    """
    List all checklists for a specific project.
    Delegates to checklist_service.
    """
    return await checklist_service.list_checklists_by_project(
        project_id, context, session, exclude
    )


async def update_checklist(
    checklist_id: UUID,
    update_request: UpdateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Update a checklist by ID.
    Delegates to checklist_service.
    """
    return await checklist_service.update_checklist(
        checklist_id, update_request, context, session
    )


async def delete_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a checklist by ID.
    Delegates to checklist_service.
    """
    await checklist_service.delete_checklist(checklist_id, context, session)


async def get_checklist_checkpoint_status(
    checklist_id: UUID,
    start_time: str,
    end_time: str,
    context: UserContext,
    session: Session,
) -> ChecklistCheckpointStatusResponse:
    """
    Get checkpoint status for a checklist within a specific time range.

    Returns the status of all active checkpoints that existed before the end of the time range,
    including their last run information within the time window or "missing" status if no run was found.

    Args:
        checklist_id: UUID of the checklist
        start_time: ISO 8601 timestamp with timezone (e.g., "2025-09-17T00:00:00-07:00")
        end_time: ISO 8601 timestamp with timezone (e.g., "2025-09-17T23:59:59.999999-07:00")
        context: User authentication context
        session: Database session

    Returns:
        ChecklistCheckpointStatusResponse with checkpoint statuses

    Raises:
        HTTPException: If timestamp format invalid, checklist not found, or authorization fails
    """
    from services.checkpoint_service._utils import TimestampValidationError

    try:
        return (
            await checklist_service.get_checklist_checkpoint_status_by_timestamp_range(
                checklist_id, start_time, end_time, context, session
            )
        )
    except TimestampValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
