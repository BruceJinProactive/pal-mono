"""
Checklist Operation Routes

This module delegates to the checklist_service for all business logic.
It only handles request/response formatting and passes through to the service layer.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.checklist import (
    Checklist,
    ChecklistHistoryResponse,
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


async def get_checklist_history(
    checklist_id: UUID,
    start_date: datetime,
    end_date: datetime,
    context: UserContext,
    session: Session,
) -> ChecklistHistoryResponse:
    """
    Get check history for a checklist within a date range.
    Delegates to checklist_service.
    """
    return await checklist_service.get_checklist_history(
        checklist_id, start_date, end_date, context, session
    )
