import uuid
from typing import List

from sqlalchemy.orm import Session

from api.models.conversation import ConversationPreview
from db.tables.messages import Message

from . import _implementation


def get_inbox_conversations(
    db: Session, account_id: uuid.UUID, max_age: int = 0
) -> List[ConversationPreview]:
    """
    Retrieves a list of conversation previews for all conversations associated with the given account.

    This function first fetches all users associated with the specified Account ID. It then retrieves
    all Conversations involving those Users and gathers information for each Conversation. Conversations
    with at least one Message are included in the result, sorted by the timestamp of the last Message
    in descending order.

    Args:
        db (Session): The database session used to perform queries.
        account_id (uuid.UUID): The unique identifier of the account for which Conversations are being retrieved.

    Returns:
        List[ConversationPreview]: A list of `ConversationPreview` objects representing the Conversations,
        each containing the Conversation ID, User ID, number of Messages, and the text of the last Message.
    """
    return _implementation.get_inbox_conversations(db, account_id, max_age)


def get_conversation_messages(
    db: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> List[Message]:
    """
    Verifies that the requester has access to the conversation, then returns all messages
    in the conversation.

    Args:
        db (Session): The database session.
        account_id (uuid.UUID): The unique identifier of the incoming request's Account.
        conversation_id (uuid.UUID): The unique identifier of the requested Conversation.

    Returns:
        List[Message]: A List of Messages from the Conversation.

    Raises:
        ValueError: If the Admin does not have access to the Conversation.
        ValueError: If the Conversation or User is not found.
    """
    return _implementation.get_conversation_messages(db, account_id, conversation_id)


def get_brandings(db: Session, account_name: str) -> list[dict]:
    """
    NOTE: This function is not implemented and is a placeholder.

    Retrieves the branding base content, formatted as a list of JSON structure, which includes branding, and frequently asked questions.

    Returns:
        list[dict]: A list of JSON dictionary containing structured information about the company's profile, branding,
        and foundational story for AI application.
    """
    return _implementation.get_brandings(db, account_name)


__all__ = [
    "get_inbox_conversations",
    "get_conversation_messages",
    "get_brandings",
]
