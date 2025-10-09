from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import FAQ
from utils.log import logger


class FAQRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_faq(self, faq: FAQ) -> FAQ:
        db_faq = FAQ()
        for key, value in vars(faq).items():
            if hasattr(FAQ, key) and key not in {
                "id",
                "created_at",
                "updated_at",
            }:
                setattr(db_faq, key, value)

        try:
            self.session.add(db_faq)
            self.session.commit()
            self.session.refresh(db_faq)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating FAQ: {e}")
            raise

        return db_faq

    def get_faq_by_id(self, faq_id: UUID) -> FAQ | None:
        try:
            return self.session.query(FAQ).filter(FAQ.id == faq_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving FAQ: {e}")
            raise

    def get_faqs_by_account_id(self, account_id: UUID) -> list[FAQ]:
        try:
            return self.session.query(FAQ).filter(FAQ.account_id == account_id).all()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving FAQs by account ID: {e}")
            raise

    def update_faq(self, faq_id: UUID, updates: dict) -> FAQ | None:
        try:
            faq = self.session.query(FAQ).filter(FAQ.id == faq_id).first()
            if not faq:
                return None

            for key, value in updates.items():
                if value is not None and hasattr(FAQ, key):
                    setattr(faq, key, value)

            self.session.commit()
            self.session.refresh(faq)
            return faq
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating FAQ: {e}")
            raise

    def delete_faq(self, faq_id: UUID) -> bool:
        try:
            faq = self.session.query(FAQ).filter(FAQ.id == faq_id).first()
            if not faq:
                return False

            self.session.delete(faq)
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting FAQ: {e}")
            raise
