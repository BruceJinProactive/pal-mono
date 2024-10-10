from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# from db.tables.feedback import Feedback
from utils.log import logger


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_feedback(self, feedback: dict):
        db_feedback = dict(
            id=feedback["id"],
            sender_email=feedback["sender_email"],
            reaction=feedback["reaction"],
            tags=feedback["tags"],
            note=feedback["note"],
            message_id=feedback["message_id"],
        )
        return db_feedback

        try:
            self.db.add(db_feedback)
            self.db.commit()
            self.db.refresh(db_feedback)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error creating feedback: {e}")
            raise

        return db_feedback
