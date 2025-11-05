"""
Checklist Service

This service contains business logic for checklist operations.
It handles authorization, validation, and orchestrates database operations.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from api.schemas.admin.checklist import (
    BatchChecklistHistoryResponse,
    Checklist,
    ChecklistHistoryResponse,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from services.auth_types import UserContext

from . import _implementation

__all__ = [
    "create_checklist",
    "get_checklist",
    "list_checklists_by_project",
    "update_checklist",
    "delete_checklist",
    "get_checklist_history",
    "get_batch_checklist_history",
]


async def create_checklist(
    project_id: UUID,
    checklist_request: CreateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Create a new checklist with authorization and validation.

    Args:
        project_id: UUID of the project
        checklist_request: Request containing checklist data
        context: User authentication context
        session: Database session

    Returns:
        Created Checklist object
    """
    return await _implementation.create_checklist(
        project_id, checklist_request, context, session
    )


async def get_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Get a checklist by ID with authorization.

    Args:
        checklist_id: UUID of the checklist
        context: User authentication context
        session: Database session

    Returns:
        Checklist object
    """
    return await _implementation.get_checklist(checklist_id, context, session)


async def list_checklists_by_project(
    project_id: UUID,
    context: UserContext,
    session: Session,
    exclude: UUID | None = None,
) -> ListChecklistsResponse:
    """
    List all checklists for a project with authorization.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session
        exclude: Optional checklist ID to exclude from results

    Returns:
        ListChecklistsResponse with checklists and total count
    """
    return await _implementation.list_checklists_by_project(
        project_id, context, session, exclude
    )


async def update_checklist(
    checklist_id: UUID,
    update_request: "UpdateChecklistRequest",
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Update a checklist with authorization.

    Args:
        checklist_id: UUID of the checklist
        update_request: Request containing update data
        context: User authentication context
        session: Database session

    Returns:
        Updated Checklist object
    """
    return await _implementation.update_checklist(
        checklist_id, update_request, context, session
    )


async def delete_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a checklist with authorization.

    Args:
        checklist_id: UUID of the checklist
        context: User authentication context
        session: Database session
    """
    await _implementation.delete_checklist(checklist_id, context, session)


async def get_checklist_history(
    checklist_id: UUID,
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
) -> ChecklistHistoryResponse:
    """
    Get check history for a checklist within a date range.

    Returns the last run for each CURRENTLY ACTIVE checkpoint in the checklist
    within the specified date range. Checkpoints that are no longer in the
    checklist are excluded.

    Args:
        checklist_id: UUID of the checklist
        start_date: Start of date range (datetime with timezone)
        end_date: End of date range (datetime with timezone)
        context: User authentication context
        session: Database session

    Returns:
        ChecklistHistoryResponse with checkpoint history and summary
    """
    return await _implementation.get_checklist_history(
        checklist_id, start_date, end_date, context, session
    )


async def get_batch_checklist_history(
    checklist_ids: list[UUID],
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
) -> BatchChecklistHistoryResponse:
    """
    Get check history for multiple checklists within a date range.

    Returns the last run for each CURRENTLY ACTIVE checkpoint in each checklist
    within the specified date range. Checkpoints that are no longer in the
    checklist are excluded.

    Args:
        checklist_ids: List of checklist UUIDs
        start_date: Start of date range (datetime with timezone)
        end_date: End of date range (datetime with timezone)
        context: User authentication context
        session: Database session

    Returns:
        BatchChecklistHistoryResponse with list of checklist history responses
    """
    return await _implementation.get_batch_checklist_history(
        checklist_ids, start_date, end_date, context, session
    )
