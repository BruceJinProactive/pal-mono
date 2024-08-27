import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Assistant
from utils.log import logger


class AssistantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_assistants(self, skip: int = 0, limit: int = 100) -> List[Assistant]:
        """Retrieve a list of assistants with pagination."""
        try:
            return self.db.query(Assistant).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving assistants: {e}")
            return []

    def get_assistant(self, assistant_id: uuid.UUID) -> Optional[Assistant]:
        """Retrieve a single assistant by its ID."""
        try:
            return self.db.query(Assistant).filter(Assistant.id == assistant_id).first()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving assistant: {e}")
            return None

    def create_assistant(self, account_id: uuid.UUID) -> Assistant:
        """Create a new assistant with a unique UUID."""
        try:
            db_assistant = Assistant(id=uuid.uuid4(), account_id=account_id)
            self.db.add(db_assistant)
            self.db.commit()
            self.db.refresh(db_assistant)
            return db_assistant
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error creating assistant: {e}")
            raise

    def update_assistant_config(
        self, assistant_id: uuid.UUID, config: Dict[str, Any]
    ) -> None:
        """Update an assistant's config in the database."""
        try:
            assistant = self.get_assistant(assistant_id)
            if assistant is None:
                raise ValueError(f"Assistant {assistant_id} not found")

            assistant.raw_config.update(config)
            self.db.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error setting assistant config: {e}")
            raise
