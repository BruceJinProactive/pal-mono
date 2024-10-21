import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from db.tables import Assistant
from utils.log import logger


class AssistantRepositoryAsync:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_assistant(self, assistant_id: uuid.UUID) -> Optional[Assistant]:
        result = await self.db.execute(
            select(Assistant)
            # [IMPORTANT] The next fixes the following error: 2024-10-21 00:17:10 {"asctime": "2024-10-21 07:17:10,747", "name": "pal-mono", "levelname": "ERROR", "message": "Error in get_chat_response: greenlet_spawn has not been called; can't call await_only() here. Was IO attempted in an unexpected place? (Background on this error at: https://sqlalche.me/e/20/xd2s)"}
            .options(selectinload(Assistant.account)).where(
                Assistant.id == assistant_id
            )
        )
        return result.scalars().first()


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

    def get_assistants_by_account(
        self, account_id: uuid.UUID
    ) -> List[Assistant] | None:
        """Retrieve a list of assistants by its account name."""
        try:
            return (
                self.db.query(Assistant)
                .filter(Assistant.account_id == account_id)
                .all()
            )
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
        """Update an assistant's config in the database.

        This function is best used to update specific fields in the configuration object.

        Args:
            assistant_id (uuid.UUID): The unique identifier of the assistant.
            config (Dict[str, Any]): The configuration dictionary to update the assistant's config with.

        Raises:
            ValueError: If the assistant with the given ID is not found.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            assistant = self.get_assistant(assistant_id)
            if assistant is None:
                raise ValueError(f"Assistant {assistant_id} not found")

            assistant.raw_config.update(config)
            self.db.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error updating assistant config: {e}")
            raise

    def replace_assistant_config(
        self, assistant_id: uuid.UUID, config: Dict[str, Any]
    ) -> None:
        """Replace an assistant's config in the database.

        This function replaces the entire `raw_config` for the specified assistant.

        Args:
            assistant_id (uuid.UUID): The unique identifier of the assistant.
            config (Dict[str, Any]): The new `raw_config` to replace the existing one.

        Raises:
            ValueError: If the assistant with the given ID is not found.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            assistant = self.get_assistant(assistant_id)
            if assistant is None:
                raise ValueError(f"Assistant {assistant_id} not found")

            assistant.raw_config = config
            self.db.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error replacing assistant config: {e}")
            raise
