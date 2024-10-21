from uuid import UUID

from sqlalchemy.orm import Session

from db.repositories.feedback_repository import FeedbackRepository

# from db.tables.feedback import Feedback


def create_feedback(db: Session, feedback: dict) -> dict:
    feedback_repository = FeedbackRepository(db)
    return feedback_repository.create_feedback(feedback)


def get_feedback_by_id(db: Session, feedback_id: UUID) -> dict:
    feedback_repository = FeedbackRepository(db)
    return feedback_repository.get_feedback_by_id(feedback_id)


def update_feedback_by_id(
    db: Session, feedback_id: UUID, updated_feedback: dict
) -> dict:
    feedback_repository = FeedbackRepository(db)
    return feedback_repository.update_feedback_by_id(feedback_id, updated_feedback)
