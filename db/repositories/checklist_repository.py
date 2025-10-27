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
    session: Session, project_id: uuid.UUID
) -> list[Checklist]:
    """
    List all checklists for a specific project.

    Args:
        session: Database session
        project_id: UUID of the project

    Returns:
        List of Checklist objects
    """
    stmt = select(Checklist).where(Checklist.project_id == project_id)
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
