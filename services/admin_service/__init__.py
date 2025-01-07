import uuid
from typing import List

from sqlalchemy.orm import Session

import db
from api.schemas.admin.conversation import ConversationPreview

from . import _implementation


def get_inbox_conversations(
    session: Session, account_id: uuid.UUID, max_age: int = 0
) -> List[ConversationPreview]:
    """
    Retrieves a list of conversation previews for all conversations associated with the given account.

    This function first fetches all users associated with the specified Account ID. It then retrieves
    all Conversations involving those Users and gathers information for each Conversation. Conversations
    with at least one Message are included in the result, sorted by the timestamp of the last Message
    in descending order.

    Args:
        session (Session): The database session used to perform queries.
        account_id (uuid.UUID): The unique identifier of the account for which Conversations are being retrieved.

    Returns:
        List[ConversationPreview]: A list of `ConversationPreview` objects representing the Conversations,
        each containing the Conversation ID, User ID, number of Messages, and the text of the last Message.
    """
    return _implementation.get_inbox_conversations(session, account_id, max_age)


def get_conversation_messages(
    session: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> List[db.Message]:
    """
    Verifies that the requester has access to the conversation, then returns all messages
    in the conversation.

    Args:
        session (Session): The database session.
        account_id (uuid.UUID): The unique identifier of the incoming request's Account.
        conversation_id (uuid.UUID): The unique identifier of the requested Conversation.

    Returns:
        List[Message]: A List of Messages from the Conversation.

    Raises:
        ValueError: If the Admin does not have access to the Conversation.
        ValueError: If the Conversation or User is not found.
    """
    return _implementation.get_conversation_messages(
        session, account_id, conversation_id
    )


def get_messages_by_conversation_id(
    session: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> List[db.Message]:
    """
    Verifies that the requester has access to the conversation, then returns all messages
    in the conversation alongside feedback for each.

    Args:
        session (Session): The database session.
        account_id (uuid.UUID): The unique identifier of the incoming request's Account.
        conversation_id (uuid.UUID): The unique identifier of the requested Conversation.

    Returns:
        List[Message]: A list of Message objects including associated feedback
    """
    return _implementation.get_messages_by_conversation_id(
        session, account_id, conversation_id
    )


def get_brand(session: Session, account_name: str) -> list[dict]:
    """
    Retrieves the brand content, formatted as a list of key value pairs.

    Returns:
        list[dict]: A list of key value pairs containing structured information about the company's profile, branding,
        and foundational story for AI application.
    """
    return _implementation.get_brand(session, account_name)


def get_knowledge_base(session: Session, account_name: str) -> list[dict]:
    """
    Retrieves the knowledge base content, formatted as a list of key value pairs.

    Args:
        session (Session): The database session.
        account_name (str): The name of the account to retrieve the knowledge base for.

    Returns:
        list[dict]: A list of key value pairs containing structured information about the company's knowledge base.

    """
    return _implementation.get_knowledge_base(session, account_name)


def get_knowledge_base_by_document_id(
    session: Session, account_name: str, document_id: str
) -> dict:
    """
    Retrieves the knowledge base content for a specific document, formatted as a dictionary.

    Args:
        session (Session): The database session.
        account_name (str): The name of the account to retrieve the knowledge base for.
        document_id (str): The unique identifier of the document.

    Returns:
        dict: A dictionary containing structured information about the company's knowledge base for the specified document.

    """
    return _implementation.get_knowledge_base_by_document_id(
        session, account_name, document_id
    )


def get_instagram_connected(session: Session, project_id: uuid.UUID) -> bool:
    """
    Check if a project has an Instagram account connected.

    Args:
        session (Session): The database session.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        bool: True if the project has an Instagram account connected, False otherwise

    Raises:
        ValueError: If the project is not found.
        RuntimeError: If there is an error checking the connection.
    """

    return _implementation.get_instagram_connected(session, project_id)


def get_instagram_username(session: Session, project_id: uuid.UUID) -> str:
    """
    Get the username of a connected Instagram account.

    Args:
        session (Session): The database session.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        str: Username of the connected Instagram account.

    Raises:
        ValueError: If the project is not found or the project is not connected to Instagram.
        RuntimeError: If there is an error getting the Instagram username.
    """

    return _implementation.get_instagram_username(session, project_id)


def set_instagram_access_token(
    session: Session,
    project_id: uuid.UUID,
    access_token: str,
    user_id: str,
    username: str,
):
    """
    Store the Instagram access token for a project in AWS Secrets Manager. If successful, also adds user_id to channel_identifiers of project.

    Args:
        session (Session): The database session.
        project_id (uuid.UUID): The unique identifier of the project.
        access_token (str): The Instagram access token.
        user_id (str): The unique identifier of the instagram account.
        username (str): The username of the instagram account.

    Returns:
        None

    Raises:
        ValueError: If the project is not found.
        RuntimeError: If there is an error storing the token.
    """

    return _implementation.set_instagram_access_token(
        session, project_id, access_token, user_id, username
    )


def remove_instagram_access_token(session: Session, project_id: uuid.UUID):
    """
    Remove the Instagram access token for a project from AWS Secrets Manager.

    Args:
        session (Session): The database session.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        None

    Raises:
        ValueError: If the project is not found.
        RuntimeError: If there is an error removing the token.
    """

    return _implementation.remove_instagram_access_token(session, project_id)


def deauthorize_instagram_access_token(session: Session, ig_user_id: str):
    """
    Deauthorize the Instagram access token for a project from AWS Secrets Manager
    using the Instagram user id.

    Args:
        session (Session): The database session.
        ig_user_id (str): The unique identifier of the Instagram user.

    Returns:
        None

    Raises:
        ValueError: If the project is not found.
        RuntimeError: If there is an error removing the token.
    """

    return _implementation.deauthorize_instagram_access_token(session, ig_user_id)


__all__ = [
    "get_inbox_conversations",
    "get_conversation_messages",
    "get_brand",
    "get_knowledge_base",
    "get_knowledge_base_by_document_id",
    "get_instagram_connected",
    "get_instagram_username",
    "set_instagram_access_token",
    "remove_instagram_access_token",
    "deauthorize_instagram_access_token",
]
