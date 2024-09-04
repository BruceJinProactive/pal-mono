import json
import re
import uuid
from typing import List

from sqlalchemy.orm import Session

from ai.assistants.gym_assistant import get_gym_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from api.models.message import AuthorType, Extras, Message, TextObject
from db.repositories.message_repository import MessageRepository
from services import assistant_service, user_service
from services.account_service import get_account

from . import _implementation


def get_chat_response(db: Session, message: Message) -> Message:
    """
    Processes an incoming message and generates a response from the appropriate assistant.

    Args:
        db (Session): The database session.
        message (Message): The incoming message object.

    Returns:
        Message: The response message object.

    Raises:
        ValueError: If any required information (account name, account, projects, user, assistant ID) is not found.
        ValueError: If the response type from the assistant is unexpected.
    """
    return _implementation.get_chat_response(db, message)


def get_messages_by_conversation(
    db: Session, conversation_id: uuid.UUID
) -> List[Message]:
    """
    Retrieves all messages for a given conversation.

    Args:
        db (Session): The database session.
        conversation_id (uuid.UUID): The unique identifier of the conversation.

    Returns:
        List[Message]: A list of Message objects associated with the conversation.
    """
    return _implementation.get_messages_by_conversation(db, conversation_id)


__all__ = ["get_chat_response", "get_messages_by_conversation"]
