import uuid

from sqlalchemy.orm import Session

import db
from api.schemas.admin.conversation import ConversationPreview

from . import _implementation


def get_inbox_conversations(
    session: Session,
    account_id: uuid.UUID,
    page: int,
    page_size: int,
    max_age: int = 0,
) -> tuple[int, list[ConversationPreview]]:
    """
    Retrieves a list of conversation previews for all conversations associated with the given account.

    This function first fetches all users associated with the specified Account ID. It then retrieves
    all Conversations involving those Users and gathers information for each Conversation. Conversations
    with at least one Message are included in the result, sorted by the timestamp of the last Message
    in descending order.

    Args:
        session (Session): The database session used to perform queries.
        account_id (uuid.UUID): The unique identifier of the account for which Conversations are being retrieved.
        page (int): The current page number (starting from 1).
        page_size (int): The number of items per page.
        max_age (int, optional): Maximum age of conversations to retrieve in days. Defaults to 0 (no limit).

    Returns:
        tuple[int, list[ConversationPreview]]: A tuple containing:
            - Total number of conversations.
            - A paginated list of `ConversationPreview` objects representing the Conversations,
              each containing the Conversation ID, User ID, number of Messages, and the text of the last Message.
    """
    return _implementation.get_inbox_conversations(
        session,
        account_id,
        max_age,
        page,
        page_size,
    )


def get_conversation_by_id(
    session: Session,
    conversation_id: uuid.UUID,
) -> db.Conversation | None:
    """
    Find the conversation that matches the given unique ID.

    Args:
        session (Session): The database session used to perform queries.
        conversation_id (uuid.UUID): The unique identifier of the conversation to find.

    Returns:
        db.Conversation | None: The matching conversation or none if id does not exist.
    """
    return _implementation.get_conversation_by_id(session, conversation_id)


def get_conversation_messages(
    session: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[db.Message]:
    """
    Verifies that the requester has access to the conversation, then returns all messages
    in the conversation.

    Args:
        session (Session): The database session.
        account_id (uuid.UUID): The unique identifier of the incoming request's Account.
        conversation_id (uuid.UUID): The unique identifier of the requested Conversation.

    Returns:
        list[Message]: A list of Messages from the Conversation.

    Raises:
        ValueError: If the Admin does not have access to the Conversation.
        ValueError: If the Conversation or User is not found.
    """
    return _implementation.get_conversation_messages(
        session, account_id, conversation_id
    )


def get_conversation_ids_by_message_ids(
    session: Session,
    message_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """
    Retrieves the conversation ID associated with each given message ID.

    Args:
        session (Session): The database session.
        message_ids (list[uuid.UUID]): A list of unique identifiers for the requested messages.

    Returns:
        dict[uuid.UUID, str]: A dictionary mapping each message ID to its conversation ID.

    Raises:
        ValueError: If a message ID does not have an associated conversation ID.
    """
    return _implementation.get_conversation_ids_by_message_ids(session, message_ids)


def get_messages_by_conversation_id(
    session: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[db.Message]:
    """
    Verifies that the requester has access to the conversation, then returns all messages
    in the conversation alongside feedback for each.

    Args:
        session (Session): The database session.
        account_id (uuid.UUID): The unique identifier of the incoming request's Account.
        conversation_id (uuid.UUID): The unique identifier of the requested Conversation.

    Returns:
        list[Message]: A list of Message objects including associated feedback
    """
    return _implementation.get_messages_by_conversation_id(
        session, account_id, conversation_id
    )


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


def update_knowledge_by_id(
    session: Session, account_name: str, document_id: str, content: str
):
    """
    Updates the knowledge base content for a specific document.

    Args:
        session (Session): The database session.
        account_name (str): The name of the account to update the knowledge base for.
        document_id (str): The unique identifier of the document.
        content (dict): The updated content for the document.

    Returns:
        None

    Raises:
        ValueError: If the document is not found.
        RuntimeError: If there is an error updating the knowledge base.
    """
    return _implementation.update_knowledge(session, account_name, document_id, content)


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
    "get_conversation_by_id",
    "get_conversation_messages",
    "get_conversation_ids_by_message_ids",
    "get_knowledge_base",
    "get_knowledge_base_by_document_id",
    "update_knowledge_by_id",
    "get_instagram_connected",
    "get_instagram_username",
    "set_instagram_access_token",
    "remove_instagram_access_token",
    "deauthorize_instagram_access_token",
]
