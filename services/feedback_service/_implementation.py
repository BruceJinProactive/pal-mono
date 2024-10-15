import uuid
from typing import Optional

from sqlalchemy.orm import Session

from db.repositories.feedback_repository import FeedbackRepository

# from db.tables.feedback import Feedback


def create_feedback(db: Session, feedback: dict) -> Optional[dict]:
    feedback_repository = FeedbackRepository(db)
    try:
        feedback["id"] = uuid.UUID(feedback["id"])
        feedback["message_id"] = uuid.UUID(feedback["message_id"])
    except ValueError as e:
        raise ValueError(f"Invalid UUID for 'id' or 'message_id': {str(e)}")
    return feedback_repository.create_feedback(feedback)


def get_feedback_by_id(db: Session, feedback_id: str) -> Optional[dict]:
    feedback_repository = FeedbackRepository(db)
    try:
        feedback_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise ValueError(f"Invalid feedback UUID: {str(e)}")
    return feedback_repository.get_feedback_by_id(feedback_uuid)


def update_feedback_by_id(
    db: Session, feedback_id: str, updated_feedback: dict
) -> Optional[dict]:
    feedback_repository = FeedbackRepository(db)
    try:
        feedback_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise ValueError(f"Invalid feedback UUID: {str(e)}")
    return feedback_repository.update_feedback_by_id(feedback_uuid, updated_feedback)
