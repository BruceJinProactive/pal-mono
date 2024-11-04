import uuid
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db.tables as db
from api.schemas.message.message import Message
from db.tables import Conversation

from . import _implementation


async def get_chat_response_async(db: AsyncSession, message: Message) -> Message:
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
    return await _implementation.get_chat_response_async(db, message)


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
) -> List[db.Message]:
    """
    Retrieves all messages for a given conversation.

    Args:
        db (Session): The database session.
        conversation_id (uuid.UUID): The unique identifier of the conversation.

    Returns:
        List[Message]: A list of Message objects associated with the conversation.
    """
    return _implementation.get_messages_by_conversation(db, conversation_id)


def get_conversations_by_user(
    db: Session, user_id: uuid.UUID, create_new_conversation: bool = False
) -> List[db.Conversation]:
    """
    Retrieves all conversations associated with a given user ID. Optionally creates a new conversation
    if no existing conversations are found and the 'create_new_conversation' flag is set to True.

    Args:
        db (Session): The database session.
        user_id (uuid.UUID): The unique identifier of the user.
        create_new_conversation (bool): Flag to determine if a new conversation should be created if none exist.

    Returns:
        List[Conversation]: A list of Conversation objects.
    """
    return _implementation.get_conversations_by_user(
        db, user_id, create_new_conversation
    )


def get_conversations_by_users(
    db: Session, user_ids: List[uuid.UUID]
) -> List[Conversation]:
    """
    Retrieves conversations associated with a list of user IDs.

    Args:
        db (Session): The database session.
        user_ids (List[uuid.UUID]): List of user IDs to retrieve conversations for.

    Returns:
        List[Conversation]: A list of conversations associated with the specified user IDs.
    """
    return _implementation.get_conversations_by_users(db, user_ids)


__all__ = [
    "get_chat_response",
    "get_messages_by_conversation",
    "get_conversations_by_user",
    "get_conversations_by_users",
]
