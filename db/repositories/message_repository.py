import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Conversation, Message, User
from utils.log import logger


class MessageRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_message(self, user_id: uuid.UUID, message_body: dict):
        # Step 1: Get the user from the database
        user = self.db.query(User).filter(User.id == user_id).first()

        # Step 2: If no such user exists, raise an error
        if not user:
            raise ValueError(f"No user found with id {user_id}")

        # Step 3: Get the first conversation from the user
        conversation = (
            self.db.query(Conversation).filter(Conversation.user_id == user.id).first()
        )

        # Step 4: If no conversation exists, create one for the user
        if not conversation:
            conversation = Conversation(user_id=user.id)
            self.db.add(conversation)
            self.db.commit()
            self.db.refresh(conversation)  # Refresh to get the new conversation ID

        # Step 5: Create a message with message_body and add it to the conversation
        message = Message(conversation_id=conversation.id, body=message_body)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)  # Refresh to get the new message ID

        return message

    def get_messages_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves all messages associated with a specific conversation id.
        Sorts them by creation timestamp so that the messages are in chronological order.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            List[Message]: A list of messages, empty if an error occurs.
        """
        try:
            messages = (
                self.db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(
                    # filter by created_at ascending so messages are in chronological order
                    Message.created_at.asc()
                )
                .all()
            )

            return messages
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving last message: {e}")
            return []

    def get_last_message_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves the most recently created message associated with a specific
        conversation id.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            Message | None: The most recent message, or None of an error occurs.
        """
        try:
            message = (
                self.db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(
                    # filter by created_at desc so first message is most recent
                    Message.created_at.desc()
                )
                .first()
            )

            if not message:
                return None

            return message
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving last message: {e}")
            return None

    def get_message_count_by_conversation(self, conversation_id: uuid.UUID):
        """
        Retrieves the number of messages associated with a specific
        conversation id.

        Args:
            conversation_id (uuid.UUID): The unique identifier for the conversation.

        Returns:
            int: The number of messages, 0 if an error occurs.
        """
        try:
            message_count = (
                self.db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .count()
            )

            return message_count
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving message count: {e}")
            return 0
