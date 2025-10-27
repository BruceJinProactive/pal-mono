"""
Checklist Service

This service contains business logic for checklist operations.
It handles authorization, validation, and orchestrates database operations.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.checklist import (
    Checklist,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)

from . import _implementation

__all__ = [
    "create_checklist",
    "get_checklist",
    "list_checklists_by_project",
    "update_checklist",
    "delete_checklist",
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
