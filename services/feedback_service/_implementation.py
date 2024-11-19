from uuid import UUID

from sqlalchemy.orm import Session

import db


def create_feedback(session: Session, feedback: dict) -> db.Feedback:
    feedback_repository = db.FeedbackRepository(session)
    return feedback_repository.create_feedback(feedback)


def get_feedback_by_id(session: Session, feedback_id: UUID) -> db.Feedback | None:
    feedback_repository = db.FeedbackRepository(session)
    return feedback_repository.get_feedback_by_id(feedback_id)


def update_feedback_by_id(
    session: Session, feedback_id: UUID, updated_feedback: dict
) -> db.Feedback:
    feedback_repository = db.FeedbackRepository(session)
    return feedback_repository.update_feedback_by_id(feedback_id, updated_feedback)
