"""
Checklist Service Implementation

Business logic for checklist operations including validation
and database operations. Authorization is handled in the API layer.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.checklist import (
    Checklist,
    CreateChecklistRequest,
    ListChecklistsResponse,
    UpdateChecklistRequest,
)
from db.repositories import checklist_repository
from services.auth_types import UserContext


def _build_checklist(checklist_db) -> Checklist:
    """
    Build a Checklist response from database model.

    Args:
        checklist_db: Database checklist object

    Returns:
        Checklist schema object
    """
    return Checklist(
        id=str(checklist_db.id),
        project_id=str(checklist_db.project_id) if checklist_db.project_id else None,
        name=checklist_db.name,
        description=checklist_db.description,
        ai_enabled=checklist_db.ai_enabled,
        created_at=checklist_db.created_at,
        updated_at=checklist_db.updated_at,
    )


async def create_checklist(
    project_id: UUID,
    checklist_request: CreateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Create a new checklist with validation.
    Authorization is handled in the API layer.

    Args:
        project_id: UUID of the project
        checklist_request: Request containing checklist data
        context: User authentication context
        session: Database session

    Returns:
        Created Checklist object
    """
    # Create the checklist with the project_id from the URL
    checklist_db = checklist_repository.create_checklist(
        session=session,
        name=checklist_request.name,
        project_id=project_id,
        description=checklist_request.description,
        ai_enabled=checklist_request.ai_enabled,
    )

    session.commit()

    return _build_checklist(checklist_db)


async def get_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Get a checklist by ID.
    Authorization is handled in the API layer.

    Args:
        checklist_id: UUID of the checklist
        context: User authentication context
        session: Database session

    Returns:
        Checklist object
    """
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    return _build_checklist(checklist_db)


async def list_checklists_by_project(
    project_id: UUID,
    context: UserContext,
    session: Session,
    exclude: UUID | None = None,
) -> ListChecklistsResponse:
    """
    List all checklists for a project.
    Authorization is handled in the API layer.

    Args:
        project_id: UUID of the project
        context: User authentication context
        session: Database session
        exclude: Optional checklist ID to exclude from results

    Returns:
        ListChecklistsResponse with checklists and total count
    """
    # Get checklists for the project
    checklists_db = checklist_repository.list_checklists_by_project(
        session, project_id, exclude
    )

    return ListChecklistsResponse(
        checklists=[_build_checklist(c) for c in checklists_db],
        total=len(checklists_db),
    )


async def update_checklist(
    checklist_id: UUID,
    update_request: UpdateChecklistRequest,
    context: UserContext,
    session: Session,
) -> Checklist:
    """
    Update a checklist.
    Authorization is handled in the API layer.

    Args:
        checklist_id: UUID of the checklist
        update_request: Request containing update data
        context: User authentication context
        session: Database session

    Returns:
        Updated Checklist object
    """
    # Get the existing checklist
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # Update the checklist
    updated_checklist = checklist_repository.update_checklist(
        session=session,
        checklist_id=checklist_id,
        name=update_request.name,
        description=update_request.description,
        ai_enabled=update_request.ai_enabled,
    )

    if not updated_checklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to update checklist {checklist_id}.",
        )

    session.commit()

    return _build_checklist(updated_checklist)


async def delete_checklist(
    checklist_id: UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a checklist.
    Authorization is handled in the API layer.

    Args:
        checklist_id: UUID of the checklist
        context: User authentication context
        session: Database session
    """
    # Get the existing checklist
    checklist_db = checklist_repository.get_checklist_by_id(session, checklist_id)

    if not checklist_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checklist {checklist_id} does not exist.",
        )

    # Delete the checklist
    deleted = checklist_repository.delete_checklist(session, checklist_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to delete checklist {checklist_id}.",
        )

    session.commit()
