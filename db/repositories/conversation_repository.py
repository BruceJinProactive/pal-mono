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

    def get_conversations_by_user(self, user_id: str):
        """
        Retrieve all conversations for a specific user.

        Args:
            user_id (str): The ID of the user whose conversations are being retrieved.

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

    def create_conversation(self, user_id: str):
        """
        Create a new conversation for a specific user.

        Args:
            user_id (str): The ID of the user for whom the conversation is being created.

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
