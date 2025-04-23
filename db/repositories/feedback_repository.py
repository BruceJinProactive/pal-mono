from uuid import UUID

from ddtrace import tracer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Feedback
from utils.log import logger


class FeedbackRepository:
    def __init__(self, session: Session):
        self.session = session

    @tracer.wrap()
    def create_feedback(self, feedback: Feedback) -> Feedback:
        db_feedback = Feedback()
        for key, value in vars(feedback).items():
            if hasattr(Feedback, key) and key not in {
                "id",
                "created_at",
                "updated_at",
            }:
                setattr(db_feedback, key, value)

        try:
            self.session.add(db_feedback)
            self.session.commit()
            self.session.refresh(db_feedback)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating feedback: {e}")
            raise

        return db_feedback

    @tracer.wrap()
    def delete_feedback_by_id(self, feedback_id: UUID) -> Feedback | None:
        try:
            db_feedback = self.get_feedback_by_id(feedback_id)
            if db_feedback is None:
                return None
            self.session.delete(db_feedback)
            self.session.commit()
            return db_feedback
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting feedback: {e}")
            raise
        except Exception as e:
            self.session.rollback()
            logger.exception(
                f"Unexpected error while deleting feedback {feedback_id}: {e}"
            )
            raise

    @tracer.wrap()
    def get_feedbacks(self) -> list[Feedback] | None:
        try:
            return self.session.query(Feedback).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving feedback: {e}")
            raise

    @tracer.wrap()
    def get_feedback_by_id(self, feedback_id: UUID) -> Feedback | None:
        try:
            return (
                self.session.query(Feedback).filter(Feedback.id == feedback_id).first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving feedback: {e}")
            raise

    @tracer.wrap()
    def update_feedback_by_id(
        self, feedback_id: UUID, updated_feedback: Feedback
    ) -> Feedback:
        try:
            db_feedback = self.get_feedback_by_id(feedback_id)
            if db_feedback is None:
                raise ValueError(f"Feedback {feedback_id} not found")
            for key, value in vars(updated_feedback).items():
                if hasattr(Feedback, key) and key not in {
                    "id",
                    "created_at",
                    "updated_at",
                }:
                    setattr(db_feedback, key, value)
            self.session.commit()
            self.session.refresh(db_feedback)
            return db_feedback
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error updating feedback: {e}")
            raise
        except Exception as e:
            self.session.rollback()
            logger.exception(
                f"Unexpected error while updating feedback {feedback_id}: {e}"
            )
            raise

    @tracer.wrap()
    def get_feedback_by_message_ids(self, message_ids: list[UUID]) -> list[Feedback]:
        try:
            return (
                self.session.query(Feedback)
                .filter(Feedback.message_id.in_(message_ids))
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving feedback by message ids: {e}")
            raise
