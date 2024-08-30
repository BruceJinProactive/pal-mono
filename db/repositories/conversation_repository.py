import uuid
from typing import List

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Conversation
from utils.log import logger


class ConversationRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_conversations(self, skip: int = 0, limit: int = 100):
        """
        Retrieve a paginated list of conversations.

        Args:
            skip (int, optional): Number of records to skip. Defaults to 0.
            limit (int, optional): Maximum number of records to return. Defaults to 100.

        Returns:
            List[Conversation] | None: A list of conversation objects, or None if an error occurs.
        """
        try:
            return self.db.query(Conversation).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving conversations: {e}")
            return None

    def get_conversations_by_user(self, user_id: uuid.UUID):
        """
        Retrieve all conversations for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user whose conversations are being retrieved.

        Returns:
            List[Conversation] | None: A list of conversation objects for the specified user, or None if an error occurs.

        Raises:
            ValueError: If 'user_id' is not provided.
        """
        if not user_id:
            raise ValueError("'user_id' must be provided")
        try:
            return (
                self.db.query(Conversation)
                .filter(Conversation.user_id == user_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving conversations by user: {e}")
            return None

    def get_conversations_by_users(
        self, user_ids: List[uuid.UUID]
    ) -> List[Conversation]:
        """
        Retrieve conversations for a list of user IDs.

        Args:
            user_ids (List[uuid.UUID]): A list of user IDs to filter conversations by.

        Returns:
            List[Conversation]: A list of Conversation objects that match the provided user IDs.
                                Returns an empty list if no matches are found or if an error occurs.
        """
        if not user_ids:
            # If no user ids are passed, return an empty list
            return []

        try:
            return (
                self.db.query(Conversation)
                .filter(Conversation.user_id.in_(user_ids))
                .all()
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving conversations by users: {e}")
            return []

    def get_conversation_by_id(self, conversation_id: uuid.UUID):
        try:
            return (
                self.db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving conversation by id: {e}")
            return None

    def create_conversation(self, user_id: uuid.UUID):
        """
        Create a new conversation for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user for whom the conversation is being created.

        Returns:
            Conversation | None: The created conversation object if successful, or None if an error occurs.

        Raises:
            ValueError: If 'user_id' is not provided.
        """
        if not user_id:
            raise ValueError("'user_id' must be provided")
        try:
            db_conversation = Conversation(user_id=user_id)
            with self.db.begin():
                self.db.add(db_conversation)
            return db_conversation
        except SQLAlchemyError as e:
            logger.error(f"Error creating conversation: {e}")
            return None
