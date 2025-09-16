import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from api.schemas.admin.conversation import ConversationPreview
from api.schemas.admin.user import SignUpRequest
from db import ConversationStatus
from services.account_service import AccountParams

from ..agent_service import AgentParams
from ..knowledge_service import KnowledgeFile
from . import _implementation, agent_prompt_generation, menu_builder
from .schema import (
    CognitoUser,
    CreatedProjectInfo,
    LeadFilters,
    LeadParams,
    ProjectSetup,
    UserSessionPreview,
)


def list_conversations_in_account(
    account_id: uuid.UUID,
    keyword: str,
    channel: str | None,
    project_id: uuid.UUID | None,
    start_date: datetime,
    end_date: datetime,
    page: int,
    page_size: int,
    escalated: bool,
    hide_testing_sessions: bool,
    db_session: Session,
) -> tuple[int, list[UserSessionPreview]]:
    return _implementation.list_conversations_in_account(
        account_id,
        keyword,
        channel,
        project_id,
        start_date,
        end_date,
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
    start_date: datetime,
    end_date: datetime,
    status: ConversationStatus | None = None,
) -> int:
    """
    Returns the number of sessions for the given user ids that match
    the given status within the specified date range. If status is not given,
    it will not filter by status.
    """
    return _implementation.get_session_count_by_user_and_status(
        session, user_ids, start_date, end_date, status
    )


def get_escalated_session_count_by_users(
    session: Session,
    user_ids: list[uuid.UUID],
    start_date: datetime,
    end_date: datetime,
) -> int:
    return _implementation.get_escalated_session_count_by_users(
        session, user_ids, start_date, end_date
    )


def onboard_new_account(
    session: Session,
    context: UserContext,
    account_name: str,
    account_params: AccountParams,
    lead_id: uuid.UUID | None,
    agent_projects: list[tuple[AgentParams, list[ProjectSetup]]],
    users: list[CognitoUser] | None = None,
) -> list[CreatedProjectInfo]:
    """
    Creates an account, agents, and projects in a single transaction.

    Args:
        session (Session): Database session
        context (UserContext): Information for the current user
        account_name (str): Name of the account to create
        account_params (AccountParams): Account parameters
        lead_id (uuid.UUID): ID of the lead that led to the onboarding
        agent_projects (list[tuple[AgentParams, list[ProjectSetup]]]):
         List of agent and project configurations
            Each item should contain:
            - agent: Agent parameters
            - projects: List of project parameters
        users (list[CognitoUser], optional): List of (email, name) tuples for creating Cognito users.

        Returns:
        list[CreatedProjectInfo]: List of created project information containing project_id,
                                   project_name, agent_id, and enable_web_widget for each project

    Raises:
        ValueError: If there's an error creating any of the entities
    """
    return _implementation.onboard_new_account(
        session, context, account_name, account_params, lead_id, agent_projects, users
    )


async def generate_agent_prompts(
    restaurant_name: str,
    agent_name: str,
    agent_type: str,
    keywords: str,
    specific_instructions: str = "",
    menu_content: str = "",
    additional_urls: list[str] | None = None,
) -> dict:
    """
    Generate agent prompts using Portkey LLM service based on restaurant and agent information.

    Args:
        restaurant_name (str): Name of the restaurant
        agent_name (str): Name of the agent
        agent_type (str): Type of agent ('general' or 'ordering')
        keywords (str): Personality keywords for the agent
        specific_instructions (str): Specific instructions for the agent
        menu_content (str): Menu content for the restaurant
        additional_urls (list[str] | None): Additional URLs to scrape for context

    Returns:
        dict: Dictionary with persona and interaction_guidelines

    Raises:
        ValueError: If there's an error generating the prompts
    """
    return await agent_prompt_generation.generate_agent_prompts(
        restaurant_name=restaurant_name,
        agent_name=agent_name,
        agent_type=agent_type,
        keywords=keywords,
        specific_instructions=specific_instructions,
        menu_content=menu_content,
        additional_urls=additional_urls or [],
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


def update_conversation(
    session: Session,
    conversation_id: uuid.UUID,
    is_escalated: bool | None,
    project_id: uuid.UUID | None,
) -> db.Conversation | None:
    """
    Update the escalation status of a conversation.

    Args:
        session (Session): The database session used to perform queries.
        conversation_id (uuid.UUID): The unique identifier of the conversation to update.
        is_escalated (bool): The new escalation status.
        project_id (uuid.UUID): The new project_id.

    Returns:
        db.Conversation | None: The updated conversation or none if id does not exist.
    """
    return _implementation.update_conversation(
        session, conversation_id, is_escalated, project_id
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


def update_lead(
    session: Session,
    context: UserContext,
    lead_id: uuid.UUID,
    params: LeadParams,
) -> db.Lead | None:
    """
    Update an existing lead.

    Args:
        session: Database session
        context: User context for authorization
        lead_id: ID of the lead to update
        params: Lead parameters to update

    Returns:
        The updated Lead object, or None if not found
    """
    return _implementation.update_lead(session, context, lead_id, params)


def delete_lead(
    session: Session,
    context: UserContext,
    lead_id: uuid.UUID,
):
    """
    Delete a lead by ID.

    Args:
        session: Database session
        context: User context for authorization
        lead_id: ID of the lead to delete

    Returns:
        True if the lead was deleted, False if not found
    """
    return _implementation.delete_lead(session, context, lead_id)


def get_lead(
    session: Session,
    context: UserContext,
    lead_id: uuid.UUID,
) -> db.Lead | None:
    """
    Get a lead by ID.

    Args:
        session: Database session
        context: User context for authorization
        lead_id: ID of the lead to retrieve

    Returns:
        The Lead object, or None if not found
    """
    return _implementation.get_lead(session, context, lead_id)


async def build_menu_from_url(
    url: str,
    use_stealth_proxy: bool = False,
) -> str:
    """
    Build menu data from a restaurant URL using Firecrawl.

    Args:
        url (str): The URL to build menu from
        use_stealth_proxy (bool): Whether to use stealth proxy for protected sites

    Returns:
        str: Menu data formatted as markdown

    Raises:
        ValueError: If there's an error building the menu
    """
    return await menu_builder.build_menu_from_url(
        url=url,
        use_stealth_proxy=use_stealth_proxy,
    )


__all__ = [
    "list_conversations_in_account",
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
    "generate_agent_prompts",
    "list_knowledge_files",
    "upload_knowledge_file",
    "delete_knowledge_file",
    "list_account_users",
    "create_account_user",
    "signup_account_user",
    "delete_account_user",
    "update_conversation",
    "list_leads",
    "create_lead",
    "update_lead",
    "delete_lead",
    "get_lead",
    "build_menu_from_url",
]
