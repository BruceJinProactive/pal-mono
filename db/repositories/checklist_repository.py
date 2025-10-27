from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.tables.checklists import Checklist


def create_checklist(
    session: Session,
    name: str,
    project_id: uuid.UUID | None = None,
    description: str | None = None,
    ai_enabled: bool = False,
) -> Checklist:
    """
    Create a new checklist in the database.

    Args:
        session: Database session
        name: Name of the checklist
        project_id: Optional project ID to associate
        description: Optional description
        ai_enabled: Whether AI is enabled

    Returns:
        The created Checklist object
    """
    checklist = Checklist(
        name=name,
        project_id=project_id,
        description=description,
        ai_enabled=ai_enabled,
    )
    session.add(checklist)
    session.flush()
    session.refresh(checklist)
    return checklist


def get_checklist_by_id(session: Session, checklist_id: uuid.UUID) -> Checklist | None:
    """
    Retrieve a checklist by its ID.

    Args:
        session: Database session
        checklist_id: UUID of the checklist

    Returns:
        Checklist object if found, None otherwise
    """
    stmt = select(Checklist).where(Checklist.id == checklist_id)
    return session.execute(stmt).scalar_one_or_none()


def list_checklists_by_project(
    session: Session,
    project_id: uuid.UUID,
    exclude: uuid.UUID | None = None,
) -> list[Checklist]:
    """
    List all checklists for a specific project.

    Args:
        session: Database session
        project_id: UUID of the project
        exclude: Optional checklist ID to exclude from results

    Returns:
        List of Checklist objects
    """
    stmt = select(Checklist).where(Checklist.project_id == project_id)

    if exclude is not None:
        stmt = stmt.where(Checklist.id != exclude)

    return list(session.execute(stmt).scalars().all())


def list_all_checklists(session: Session) -> list[Checklist]:
    """
    List all checklists.

    Args:
        session: Database session

    Returns:
        List of all Checklist objects
    """
    stmt = select(Checklist)
    return list(session.execute(stmt).scalars().all())


def update_checklist(
    session: Session,
    checklist_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    ai_enabled: bool | None = None,
) -> Checklist | None:
    """
    Update a checklist by its ID.

    Args:
        session: Database session
        checklist_id: UUID of the checklist
        name: Optional new name
        description: Optional new description
        ai_enabled: Optional new AI enabled status

    Returns:
        Updated Checklist object if found, None otherwise
    """
    checklist = get_checklist_by_id(session, checklist_id)
    if not checklist:
        return None

    if name is not None:
        checklist.name = name
    if description is not None:
        checklist.description = description
    if ai_enabled is not None:
        checklist.ai_enabled = ai_enabled

    session.flush()
    session.refresh(checklist)
    return checklist


def delete_checklist(session: Session, checklist_id: uuid.UUID) -> bool:
    """
    Delete a checklist by its ID.

    Args:
        session: Database session
        checklist_id: UUID of the checklist

    Returns:
        True if deleted, False if not found
    """
    checklist = get_checklist_by_id(session, checklist_id)
    if not checklist:
        return False

    session.delete(checklist)
    session.flush()
    return True
