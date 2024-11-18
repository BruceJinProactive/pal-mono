from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Feedback
from utils.log import logger


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_feedback(self, feedback: dict) -> Feedback:
        db_feedback = Feedback(
            author_identifier=feedback["author_identifier"],
            reaction=feedback["reaction"],
            tags=feedback["tags"],
            note=feedback["note"],
            message_id=feedback["message_id"],
        )

        try:
            self.db.add(db_feedback)
            self.db.commit()
            self.db.refresh(db_feedback)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error creating feedback: {e}")
            raise

        return db_feedback

    def get_feedback_by_id(self, feedback_id: UUID) -> Feedback | None:
        try:
            return self.db.query(Feedback).filter(Feedback.id == feedback_id).first()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving feedback: {e}")
            raise

    def update_feedback_by_id(
        self, feedback_id: UUID, updated_feedback: dict
    ) -> Feedback:
        try:
            db_feedback = self.get_feedback_by_id(feedback_id)
            if db_feedback is None:
                raise ValueError(f"Feedback {feedback_id} not found")
            for key, value in updated_feedback.items():
                setattr(db_feedback, key, value)
            self.db.commit()
            self.db.refresh(db_feedback)
            return db_feedback
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error updating feedback: {e}")
            raise
        except Exception as e:
            self.db.rollback()
            logger.exception(
                f"Unexpected error while updating feedback {feedback_id}: {e}"
            )
            raise

    def get_feedback_by_message_ids(self, message_ids: list[UUID]) -> list[Feedback]:
        try:
            return (
                self.db.query(Feedback)
                .filter(Feedback.message_id.in_(message_ids))
                .all()
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving feedback by message ids: {e}")
            raise
