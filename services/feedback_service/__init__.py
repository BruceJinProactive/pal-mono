from typing import Optional

from sqlalchemy.orm import Session

from . import _implementation

# from db.tables.feedback import Feedback


def create_feedback(db: Session, feedback: dict) -> Optional[dict]:
    """
    Creates feedback in the database.

    Args:
        db (Session): The database session.
        feedback (dict): The feedback to create.

    Returns:
        Feedback: The DB Feedback object created
    """
    return _implementation.create_feedback(db, feedback)


__all__ = ["create_feedback"]
