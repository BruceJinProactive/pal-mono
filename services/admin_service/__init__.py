import datetime
import uuid
from typing import Union

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from api.schemas.admin.conversation import ConversationPreview
from db import ConversationStatus
from db.tables.order_integration import OrderIntegrationVendor, OrderProtocol
from services.account_service import AccountParams

from ..agent_service import AgentParams
from ..knowledge_service import KnowledgeFile
from . import _implementation
from .schema import (
    CognitoUser,
    LeadFilters,
    LeadParams,
    ProjectSetup,
    UserSessionPreview,
)


def list_user_sessions_in_account(
    account_id: uuid.UUID,
    keyword: str,
    channel: str | None,
    min_create_time: datetime.datetime | None,
    page: int,
    page_size: int,
    escalated: bool,
    hide_testing_sessions: bool,
    db_session: Session,
) -> tuple[int, list[UserSessionPreview]]:
    return _implementation.list_user_sessions_in_account(
        account_id,
        keyword,
        channel,
        min_create_time,
        page,
        page_size,
        escalated,
        hide_testing_sessions,
        db_session,
    )


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
    session: Session,
    account_id: uuid.UUID,
    conversation_id: uuid.UUID,
    sort_desc: bool = False,
) -> list[db.Message]:
    """
    Verifies that the requester has access to the conversation, then returns all messages
    in the conversation.

    Args:
        session (Session): The database session.
        account_id (uuid.UUID): The unique identifier of the incoming request's Account.
        conversation_id (uuid.UUID): The unique identifier of the requested Conversation.
        sort_desc (bool): Changes the sort order to reverse-chronological so last message
            appears first.

    Returns:
        list[Message]: A list of Messages from the Conversation.

    Raises:
        ValueError: If the Admin does not have access to the Conversation.
        ValueError: If the Conversation or User is not found.
    """
    return _implementation.get_conversation_messages(
        session, account_id, conversation_id, sort_desc
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


def get_session_count_by_user_and_status(
    session: Session,
    user_ids: list[uuid.UUID],
    min_create_time: datetime.datetime,
    status: ConversationStatus | None = None,
) -> int:
    """
    Returns the number of sessions or the given user ids that match
    the given status. If status is not given, it will not filter by
    status.
    """
    return _implementation.get_session_count_by_user_and_status(
        session, user_ids, min_create_time, status
    )


def get_escalated_session_count_by_users(
    session: Session,
    user_ids: list[uuid.UUID],
    min_create_time: datetime.datetime,
) -> int:
    return _implementation.get_escalated_session_count_by_users(
        session, user_ids, min_create_time
    )


def onboard_new_account(
    session: Session,
    context: UserContext,
    account_name: str,
    account_params: AccountParams,
    agent_projects: list[tuple[AgentParams, list[ProjectSetup]]],
    users: list[CognitoUser] | None = None,
) -> str:
    """
    Creates an account, agents, and projects in a single transaction.

    Args:
        session (Session): Database session
        context (UserContext): Information for the current user
        account_name (str): Name of the account to create
        account_params (AccountParams): Account parameters
        agent_projects (list[tuple[AgentParams, list[ProjectSetup]]]):
         List of agent and project configurations
            Each item should contain:
            - agent: Agent parameters
            - projects: List of project parameters
        users (list[CognitoUser], optional): List of (email, name) tuples for creating Cognito users.

    Raises:
        ValueError: If there's an error creating any of the entities
    """
    return _implementation.onboard_new_account(
        session, context, account_name, account_params, agent_projects, users
    )


def upload_knowledge_file(
    session: Session,
    context: UserContext,
    target: db.Project | db.Agent,
    file_name: str,
    content: bytes,
):
    """
    Upload a text file to the project's knowledge base.
    This function gets the knowledge settings from the project's raw_config,
    generates embeddings for the text content, and stores them in Pinecone.

    Args:
        session (Session): The database session.
        context (UserContext): Information for the current user.
        target (db.Project | db.Agent): The target to upload knowledge file for.
        file_name (str): The name of the file to upload.
        content (str): The text content of the file.

    Returns:
        dict: A dictionary containing a success message and the document ID.

    Raises:
        ValueError: If the project is not found or knowledge is not configured.
        RuntimeError: If there is an error uploading the file.
    """
    return _implementation.upload_project_knowledge(
        session, context, target, file_name, content
    )


def list_knowledge_files(
    session: Session,
    context: UserContext,
    target: db.Project | db.Agent,
    filename: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[int, list[KnowledgeFile]]:
    """
    Retrieve a list of knowledge file data for a specific project with pagination.

    Args:
        session: The database session
        context (UserContext): Information for the current user.
        target: The project or agent to retrieve knowledge files for
        filename: Optional filename to filter results by (case-insensitive partial match)
        offset: The number of files to skip
        limit: The maximum number of files to return

    Returns:
        tuple[int, list[dict]]: A tuple containing the total number of files and a list of file data

    Raises:
        ValueError: If the project is not found.
        RuntimeError: If there is an error retrieving the files.
    """
    return _implementation.list_knowledge_files(
        session, context, target, filename, offset, limit
    )


def delete_knowledge_file(
    session: Session,
    context: UserContext,
    target: db.Project | db.Agent,
    filename: str,
) -> list[str]:
    """
    Delete a knowledge file from the knowledge base specified by the
    knowledge_config. This function deletes the file from the Pinecone index.

    Args:
        session (Session): The database session.
        context (UserContext): Information for the current user.
        target (Union[db.Project | db.Agent]): The project or agent that this delete happens to.
        filename (str): The name of the file to delete.

    Returns:
        list[str]: List of embedding IDs that are deleted.
    """
    return _implementation.delete_knowledge_file(session, context, target, filename)


def list_account_users(account_name: str) -> list[CognitoUser]:
    """
    List all admin users for a specific account.

    Args:
        account_name: The name of the account to list users for

    Returns:
        list[CognitoUser]: A list of admin users for the account

    Raises:
        ValueError: If there's an error listing Cognito users
    """
    return _implementation.list_account_users(account_name)


def create_account_user(
    account_name: str,
    user_email: str,
    user_name: str,
) -> CognitoUser:
    """
    Create Cognito user accounts for the provided list of users using AdminCreateUser.

    Args:
        account_name (str): The account name to associate the users with
        user_email (str): User's email used for login
        user_name (str): User's first name

    Returns:
        CognitoUser: Created user details

    Raises:
        ValueError: If there's an error creating a user account
    """
    return _implementation.create_account_user(account_name, user_email, user_name)


def signup_account_user(
    account_name: str,
    user_email: str,
    user_name: str,
    password: str,
) -> CognitoUser:
    """
    Create Cognito user accounts for the provided list of users using AdminCreateUser.

    Args:
        account_name (str): The account name to associate the users with
        user_email (str): User's email used for login
        user_name (str): User's first name
        password (str): User's password

    Returns:
        CognitoUser: Created user details

    Raises:
        ValueError: If there's an error creating a user account
    """
    return _implementation.signup_account_user(
        account_name, user_email, user_name, password
    )


def delete_account_user(account_name: str, user_email: str) -> None:
    """
    Delete an admin user for a specific account.

    Args:
        account_name: The name of the account the user belongs to
        user_email: The user ID (email) to delete

    Raises:
        ValueError: If the user is not found or there's an error deleting the user
    """
    return _implementation.delete_account_user(account_name, user_email)


def setup_project_order_integration(
    session: Session,
    context: UserContext,
    project: db.Project,
    protocol: OrderProtocol,
    destination: str,
    vendor: OrderIntegrationVendor | None = None,
) -> db.OrderIntegration:
    """
    Creates or updates the order integration for the specified project.

    Args:
        session (Session): The database session to use.
        context (UserContext): The user context for the authenticated user.
        project (db.Project): The project to create the order integration for.
        protocol (OrderProtocol): The protocol to use for order placement.
        destination (str): The destination address to send orders to.
        vendor (OrderIntegrationVendor): The vendor to use for order processing.

    Returns:
        db.OrderIntegration: The created or updated order integration.

    Raises:
        Exception: If there's an error creating or updating the order integration.
    """
    return _implementation.setup_project_order_integration(
        session, context, project, protocol, destination, vendor
    )


def list_leads(
    session: Session,
    filter_params: LeadFilters,
) -> tuple[list[db.Lead], int]:
    """
    Retrieve a paginated list of leads with optional filters.

    Args:
        session: Database session
        filter_params: Filter parameters including pagination and search criteria

    Returns:
        Tuple of (leads list, total count)
    """
    return _implementation.list_leads(session, filter_params)


def create_lead(
    session: Session,
    context: UserContext,
    params: LeadParams,
) -> db.Lead:
    """
    Create a new lead.

    Args:
        session: Database session
        context: User context for authorization
        params: Lead parameters including business_name (required) and other optional fields

    Returns:
        The created Lead object
    """
    return _implementation.create_lead(session, context, params)


__all__ = [
    "list_user_sessions_in_account",
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
    "get_session_count_by_user_and_status",
    "get_escalated_session_count_by_users",
    "onboard_new_account",
    "list_knowledge_files",
    "upload_knowledge_file",
    "delete_knowledge_file",
    "list_account_users",
    "create_account_user",
    "signup_account_user",
    "delete_account_user",
    "setup_project_order_integration",
    "list_leads",
    "create_lead",
]
