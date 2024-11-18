from uuid import UUID

from sqlalchemy.orm import Session

from db.tables import Feedback

from . import _implementation


def create_feedback(db: Session, feedback: dict) -> Feedback:
    """
    Creates feedback in the database.

    Args:
        db (Session): The database session.
        feedback (dict): The feedback to create.

    Returns:
        Feedback: The DB Feedback object created
    """
    return _implementation.create_feedback(db, feedback)


def get_feedback_by_id(db: Session, feedback_id: UUID) -> Feedback | None:
    """
    Retrieves feedback by id from the database.

    Args:
        db (Session): The database session.
        feedback_id (UUID): The feedback to retrieve.

    Returns:
        Feedback | None: The DB Feedback object associated with the id if it exists else None
    """
    return _implementation.get_feedback_by_id(db, feedback_id)


def update_feedback_by_id(
    db: Session, feedback_id: UUID, updated_feedback: dict
) -> Feedback:
    """
    Updates feedback by id in the database.

    Args:
        db (Session): The database session.
        feedback_id (UUID): The feedback to update.
        updated_feedback (dict): The updated feedback fields.

    Returns:
        Feedback: The updated DB Feedback object associated with the id if it exists
    """
    return _implementation.update_feedback_by_id(db, feedback_id, updated_feedback)


__all__ = [
    "create_feedback",
    "get_feedback_by_id",
    "update_feedback_by_id",
]
