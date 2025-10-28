import json
import os
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import boto3
import requests
from botocore.exceptions import ClientError
from firecrawl import Firecrawl
from pydantic import BaseModel
from sqlalchemy import Table
from sqlalchemy.orm import Session, declarative_base

import db
from api.routes.admin import UserContext
from api.schemas.admin.conversation import ConversationPreview
from db.repositories import LeadFilter as RepoLeadFilter
from db.repositories.conversation_repository import ConversationUpdate
from services import (
    account_service,
    agent_service,
    email_service,
    knowledge_service,
    project_service,
    subscription_service,
    user_service,
)
from services.account_service import AccountParams
from services.admin_service._utils import generate_password, get_knowledge_settings
from services.admin_service.schema import (
    CognitoUser,
    CognitoUserSession,
    CreatedProjectInfo,
    LeadFilters,
    LeadParams,
    ProjectSetup,
    UserSessionPreview,
)
from services.agent_service import AgentParams
from services.knowledge_service import KnowledgeFile
from services.message_service import (
    get_conversations_by_users,
    get_messages_by_conversation,
)
from services.project_service import get_project, replace_project_channel_identifiers
from services.user_service import get_users_by_account_id
from utils import secret
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

MOCK_USER_PREFIX = "mock-user"


AWS_REGION = os.environ["AWS_REGION"]
AWS_ADMIN_CONSOLE_USER_POOL_ID = os.environ["AWS_ADMIN_CONSOLE_USER_POOL_ID"]
AWS_ADMIN_CONSOLE_APP_CLIENT_ID = os.environ["AWS_ADMIN_CONSOLE_APP_CLIENT_ID"]


def _include_conversation_preview(message: db.Message, max_age: int) -> bool:
    """
    An internal filter function that determines whether a conversation should be included in get_inbox_conversations
    The conversation cannot be older than max_age, if specified.

    Args:
        message: The conversation's last message
        max_age: age limit in minutes. 0 by default (meaning no limit) as provided in __init__.py
    Returns:
        bool: whether to include the conversation
    """
    if max_age:
        return message.created_at >= datetime.now(timezone.utc) - timedelta(
            minutes=max_age
        )

    return True


def get_conversation_by_id(
    session: Session,
    conversation_id: uuid.UUID,
) -> db.Conversation | None:
    conversation_repository = db.ConversationRepository(session)
    conversation = conversation_repository.get_conversation_by_id(conversation_id)
    return conversation


def list_conversations_in_account(
    account_id: uuid.UUID,
    keyword: str,
    channel: str | None,
    language: list[str] | None,
    purpose: list[str] | None,
    ended_reason: list[str] | None,
    customer_converted: bool | None,
    project_id: uuid.UUID | None,
    start_date: datetime | None,
    end_date: datetime,
    page: int,
    page_size: int,
    escalated: bool,
    hide_testing_sessions: bool,
    db_session: Session,
) -> tuple[int, list[UserSessionPreview]]:
    message_repository = db.MessageRepository(db_session)
    conversation_repository = db.ConversationRepository(db_session)

    # Retrieve all user sessions on the requested page
    account_users = user_service.get_users_by_account_id(db_session, account_id)
    account_users_ids = [user.id for user in account_users]
    all_session_ids = conversation_repository.get_conversation_ids_by_user_ids(
        account_users_ids,
        start_date,
        end_date,
        project_id,
        hide_testing_sessions,
        language,
        purpose,
        ended_reason,
        customer_converted,
    )
    # Only narrow down id list if necessary
    if keyword or channel or escalated:
        filtered_session_ids = message_repository.filter_sessions_by_keyword(
            all_session_ids, keyword, channel, escalated
        )
    else:
        filtered_session_ids = all_session_ids
    total, sessions = conversation_repository.get_paginated_sessions_by_ids(
        filtered_session_ids,
        offset=(page - 1) * page_size,
        limit=page_size,
    )

    # Build the session previews
    user_session_previews = [
        UserSessionPreview(
            conversation=session,
            last_message=message_repository.get_last_user_message_by_conversation(
                session.id
            )
            or message_repository.get_last_message_by_conversation(session.id),
            message_count=message_repository.get_message_count_by_conversation(
                session.id
            ),
        )
        for session in sessions
    ]
    return total, user_session_previews


def get_conversation_filter_values(
    account_id: uuid.UUID, db_session: Session
) -> tuple[list[str], list[str], list[str]]:
    """
    Get distinct filter values for conversations in an account.

    Returns:
        tuple: (languages, purposes, ended_reasons)
    """
    conversation_repository = db.ConversationRepository(db_session)
    return conversation_repository.get_distinct_filter_values(account_id)


def get_inbox_conversations(
    session: Session, account_id: uuid.UUID, max_age: int, page: int, page_size: int
) -> tuple[int, list[ConversationPreview]]:
    # Get users associated with the account
    users = get_users_by_account_id(session, account_id=account_id)

    # Get all conversations involving a user with the account id
    total_conversations, conversations = get_conversations_by_users(
        session, page, page_size, user_ids=list(map(lambda user: user.id, users))
    )
    conversation_user_ids = list(
        map(lambda conv: (conv.id, conv.user_id), conversations)
    )

    message_counts: dict[uuid.UUID, int] = {}
    last_messages: dict[uuid.UUID, db.Message] = {}
    escalated_conversations: dict[uuid.UUID, bool] = {}

    message_repository = db.MessageRepository(session)
    for id, _ in conversation_user_ids:
        # Get most recent message for each conversation generated by a user
        last_message = message_repository.get_last_user_message_by_conversation(id)

        # If there are no messages, skip this conversation
        if last_message is None or last_message.body is None:
            continue

        # If the last message is from the testing phone number, skip this conversation
        if (
            last_message.body.get("sender_identifier", "") == "+16692463752"
            or last_message.body.get("sender_identifier", "") == "+14384973894"
        ):
            continue

        # If the last message ends with "latest" or "staging", skip this conversation
        if not last_message.body.get("text"):
            continue

        last_message_text = last_message.body.get("text", {}).get("body", "").lower()
        if re.search(r"\b(?:latest|staging)\b$", last_message_text):
            continue

        last_messages[id] = last_message

        # Get most number of messages for each conversation
        message_counts[id] = message_repository.get_message_count_by_conversation(id)

        # Check if the conversation is escalated
        is_escalated = message_repository.is_conversation_escalated(id)

        escalated_conversations[id] = is_escalated

    # Filter conversations by recency of last message, and sort descending by created_at
    conversation_previews = sorted(
        filter(
            lambda preview: _include_conversation_preview(preview[3], max_age),
            [
                (
                    id,
                    user_id,
                    message_counts[id],
                    last_messages[id],
                    last_messages[id].created_at,
                    escalated_conversations[id],
                )
                for id, user_id in conversation_user_ids
                if id in message_counts and id in last_messages
            ],
        ),
        key=lambda preview: preview[4],
        reverse=True,
    )

    def _get_last_message_details(message: db.Message):
        """Extracts relevant message details including text, media, channel, sender, recipient, and broker."""
        last_message_text = ""

        # Extract text if available
        if message.body.get("text") is not None:
            last_message_text = message.body.get("text", {}).get("body", "")
        # Extract media URL if text is unavailable
        elif message.body.get("media") is not None:
            last_message_text = message.body.get("media", {}).get("url", "")

        channel = message.body.get("channel", "")
        sender_identifier = message.body.get("sender_identifier", "")
        recipient_identifier = message.body.get("recipient_identifier", "")
        broker = message.body.get("broker", None)

        return (
            last_message_text,
            channel,
            sender_identifier,
            recipient_identifier,
            broker,
        )  # type: ignore

    # Reformat conversations
    inbox: list[ConversationPreview] = [
        ConversationPreview(
            id=str(conversation[0]),
            user_id=str(conversation[1]),
            num_messages=conversation[2],
            last_message_text=last_text,
            channel=channel,
            sender_identifier=sender_identifier,
            recipient_identifier=recipient_identifier,
            broker=broker,
            created_at=conversation[4],
            is_escalated=conversation[5],
        )
        for conversation in conversation_previews
        for last_text, channel, sender_identifier, recipient_identifier, broker in [
            _get_last_message_details(conversation[3])
        ]
    ]

    return total_conversations, inbox


def get_conversation_messages(
    session: Session,
    account_id: uuid.UUID,
    conversation_id: uuid.UUID,
    sort_desc: bool = False,
) -> list[db.Message]:
    conversation_repository = db.ConversationRepository(session)
    user_repository = db.UserRepository(session)

    """
    First we need to ensure that the requesting Account can access this Conversation.
    For example, if a Client A's Admin types in a random UUID that corresponds to a Conversation
    from Client B, A's Admin should not be able to access it.
    """

    # Get the Account ID associated with the Conversation ID
    conversation = conversation_repository.get_conversation_by_id(conversation_id)

    if not conversation:
        raise ValueError("Conversation not found.")

    user = user_repository.get_user_by_id(conversation.user_id)

    if not user:
        raise ValueError("User not found.")

    # If the Account IDs do not match, the Admin does not have access to this Conversation
    if user.account_id != account_id:
        raise ValueError(
            "Account ID of Conversation and requesting Account do not match."
        )

    # Requesting Account matches Account associated with Conversation, so get messages and return
    messages = get_messages_by_conversation(session, conversation_id=conversation_id)

    # Sort messages by timestamp
    messages.sort(
        key=lambda m: (
            0 if isinstance(m, str) else 1,
            (
                m
                if isinstance(m, str)
                else m.body.get("timestamp", str(m.created_at or datetime.min))
            ),
        ),
        reverse=sort_desc,
    )

    return messages


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
    message_repository = db.MessageRepository(session)

    # Create a mapping of message IDs to conversation IDs
    result = {}
    for message_id in message_ids:
        conversation_id = message_repository.get_conversation_id_by_message_id(
            message_id=message_id
        )
        if not conversation_id:
            raise ValueError(f"Conversation not found for message ID: {message_id}")
        result[message_id] = str(conversation_id)

    return result


def get_knowledge_base(session: Session, account_name: str) -> list:
    Base = declarative_base()

    if not account_name:
        raise ValueError("Account not found.")

    try:
        # Dynamically get the table name
        table_name = f"{account_name}_knowledge_agno"

        # Fetch the table dynamically by reflecting the table from the database schema
        knowledge_table = Table(
            table_name, Base.metadata, autoload_with=session.bind, schema="ai"
        )

        # Query the dynamically selected table
        knowledge_base_list = session.query(knowledge_table).all()

        # Map results into a list of dictionaries
        knowledge_base_list = [
            {
                "content": item.content,
                "id": item.id,
                "name": item.name,
                "created_at": item.created_at,
            }
            for item in knowledge_base_list
        ]

        return knowledge_base_list

    except Exception as e:
        logger.error(f"Unable to get knowledge base: {e}")
        raise RuntimeError("Unable to get knowledge base.") from e


def get_knowledge_base_by_document_id(
    session: Session, account_name: str, document_id: str
) -> dict:
    knowledge = get_knowledge_base(session, account_name)
    if not knowledge:
        return {}
    for item in knowledge:
        if item["id"] == document_id:
            return item
    return {}


def update_knowledge(
    session: Session, account_name: str, knowledge_id: str, content: str
) -> None:
    """
    Update AI knowledge content by the knowledge ID.

    Args:
        session (Session): The session to use.
        account_name (str): The account name to retrieve the AI knowledge for.
        knowledge_id (str): The ID of the knowledge to update.
        content (str): The new content to update the AI knowledge with.

    Returns:
        KnowledgeBase | None: The updated AI knowledge or None if no such knowledge is found.
    """
    Base = declarative_base()

    if not account_name:
        raise ValueError("Account not found.")

    try:
        table_name = f"{account_name}_knowledge_agno"

        knowledge_table = Table(
            table_name, Base.metadata, autoload_with=session.bind, schema="ai"
        )

        result = session.execute(
            knowledge_table.update()
            .where(knowledge_table.c.id == knowledge_id)
            .values(content=content)
        )

        if result.rowcount == 0:
            raise ValueError("Knowledge not found.")

        session.commit()
        logger.info("Knowledge updated successfully.")

    except Exception as e:
        logger.error(f"Unable to update knowledge by ID: {e}")
        raise RuntimeError("Unable to update knowledge by ID.") from e


def _project_name_to_ig_access_token_key(project_name: str) -> str:
    return f"{project_name.upper()}_INSTAGRAM_ACCESS_TOKEN"


def _ig_user_id_to_ig_project_name_key(user_id: str) -> str:
    return f"INSTAGRAM_USER_{user_id}_PROJECT_KEY"


def _parse_ig_project_secret_value(secret_value) -> dict:
    try:
        if not isinstance(secret_value, dict):
            secret_dict = json.loads(secret_value)
        else:
            secret_dict = secret_value

        return secret_dict
    except Exception as e:
        logger.error(f"Unable to parse project secret value: {e}")
        raise RuntimeError("Unable to parse project secret value.") from e


def get_instagram_connected(session: Session, project_id: uuid.UUID) -> bool:
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    project_secret_key = _project_name_to_ig_access_token_key(project.name)
    try:
        # if successful, then the key exists, and hence the project is connected
        secret.get_client_secret(project_secret_key)
        return True
    except KeyError:
        # if the key does not exist, then the project is not connected
        return False
    except Exception as e:
        # if any other error occurs, log and raise
        logger.error(f"Unable to get Instagram access token: {e}")
        raise RuntimeError(f"Unable to get Instagram access token: {e}")


def get_instagram_username(session: Session, project_id: uuid.UUID) -> str:
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    project_secret_key = _project_name_to_ig_access_token_key(project.name)

    # Ensure the project is connected to Instagram
    try:
        # if successful, then the key exists, and hence the project is connected
        secret_value = secret.get_client_secret(project_secret_key)
    except KeyError:
        # if the key does not exist, then the project is not connected
        # log and raise
        logger.error("Project is not connected to Instagram.")
        raise ValueError("Project is not connected to Instagram.")
    except Exception as e:
        # if any other error occurs, log and raise
        logger.error(f"Unable to get Instagram access token: {e}")
        raise RuntimeError(f"Unable to get Instagram access token: {e}")

    try:
        secret_dict = _parse_ig_project_secret_value(secret_value)
    except RuntimeError as e:
        logger.error(f"Unable to parse project secret value: {e}")
        raise RuntimeError("Unable to parse project secret value.") from e

    return secret_dict.get("username", "")


def set_instagram_access_token(
    session: Session,
    project_id: uuid.UUID,
    access_token: str,
    user_id: str,
    username: str,
) -> None:
    """
    Add both project and user secrets atomically, with rollback attempt if necessary
    """
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    project_secret_key = _project_name_to_ig_access_token_key(project.name)
    project_secret_value = json.dumps(
        {"access_token": access_token, "user_id": user_id, "username": username}
    )

    user_secret_key = _ig_user_id_to_ig_project_name_key(user_id)
    user_secret_value = project_secret_key

    # Add secrets, and rollback if necessary
    try:
        # Attempt to add both secrets one by one
        secret.add_client_secret(project_secret_key, project_secret_value)

        # Temporary solution to try to avoid versioning errors
        time.sleep(5)

        try:
            secret.add_client_secret(user_secret_key, user_secret_value)
        except Exception as add_e:
            # Rollback first secret if second secret fails
            logger.error(
                f"Unable to add user secret, try rolling back project secret: {add_e}"
            )
            try:
                secret.remove_client_secret(project_secret_key)
            except Exception as rollback_e:
                logger.error(f"Unable to roll back project secret: {rollback_e}")
                raise RuntimeError(
                    "Unable to roll back project secret."
                ) from rollback_e
            raise RuntimeError(
                "Unable to add user secret, succsesfully rolled back project secret."
            ) from add_e
    except KeyError as e:
        # If the project_secret_key already exists, check whether the user_secret_key exists
        logger.error(e)
        try:
            # if user_secret_key exists as well, then the project is already connected
            secret.get_client_secret(user_secret_key)
        except KeyError as get_e:
            # If the project_secret_key exists but the user_secret_key does not, something went wrong
            logger.error(
                f"Inconsistent state, project secret exists but user secret does not: {get_e}"
            )
            raise RuntimeError(
                "Inconsistent state, project secret exists but user secret does not."
            ) from get_e
        except Exception as get_e:
            # Log error and raise
            logger.error(f"Unable to verify if user secret exists : {get_e}")
            raise RuntimeError("Unable to verify if user secret exists.") from get_e
    except Exception as e:
        logger.error(f"Unable to set Instagram access token: {e}")
        raise RuntimeError("Unable to set Instagram access token.") from e

    try:
        channel_identifiers = project.channel_identifiers

        # Modifying the existing array does not work, copy to new array instead
        new_channel_identifiers = []
        if channel_identifiers:
            for channel_identifier in channel_identifiers:
                new_channel_identifiers.append(channel_identifier)

        # Add the new channel identifier for the connected instagram account
        instagram_channel_identifier = f"instagram:{user_id}"
        if instagram_channel_identifier not in new_channel_identifiers:
            new_channel_identifiers.append(instagram_channel_identifier)
        replace_project_channel_identifiers(
            session, project_id, new_channel_identifiers
        )
    except Exception as e:
        logger.error(f"Unable to update project channel identifiers: {e}")
        raise RuntimeError("Unable to update project channel identifiers.") from e


def remove_instagram_access_token(session: Session, project_id: uuid.UUID) -> None:
    """
    Remove both project and user secrets using the project secret key
    """
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    project_secret_key = _project_name_to_ig_access_token_key(project.name)

    try:
        secret_value = secret.get_client_secret(project_secret_key)
    except KeyError as e:
        # if the key does not exist, then the project is not connected
        logger.error(e)
        return
    except Exception as e:
        logger.error(f"Unable to remove Instagram access token: {e}")
        raise RuntimeError(f"Unable to remove Instagram access token: {e}")

    try:
        secret_dict = _parse_ig_project_secret_value(secret_value)
    except RuntimeError as e:
        logger.error(f"Unable to parse project secret value: {e}")
        raise RuntimeError("Unable to parse project secret value.") from e

    ig_user_id = secret_dict.get("user_id", "")
    if not ig_user_id:
        raise RuntimeError("Instagram user ID not found in project secret.")

    user_secret_key = _ig_user_id_to_ig_project_name_key(ig_user_id)

    try:
        # Remove both secrets
        secret.remove_client_secret(project_secret_key)

        # Temporary solution to try to avoid versioning errors
        time.sleep(5)

        try:
            secret.remove_client_secret(user_secret_key)
        except KeyError as e:
            # if the user_secret_key does not exist, log and continue
            logger.error(
                f"user secret {user_secret_key} does not exist, continuing: {e}"
            )
        except Exception as e:
            logger.error(f"Unable to remove user secret: {e}")
            raise RuntimeError("Unable to remove user secret.") from e
    except KeyError as e:
        # If the project_secret_key does not exist, check whether the user_secret_key exists
        logger.error(
            f"project secret does not exist, checking whether user secret exists: {e}"
        )

        try:
            secret.get_client_secret(user_secret_key)
        except KeyError as get_e:
            # Neither keys exists, so the project was already disconnected
            logger.error(
                f"Neither project secret nor user secret exist, continuing: {get_e}"
            )
            return
        except Exception as get_e:
            # Log error and raise
            logger.error(f"Unable to verify if user secret exists: {get_e}")
            raise RuntimeError("Unable to verify if user secret exists.") from get_e

        # if user_secret_key exists, log data inconsistency
        logger.error(
            "Inconsistent state, user secret exists but project secret does not."
        )
        raise RuntimeError(
            "Inconsistent state, user secret exists but project secret does not."
        )
    except Exception as e:
        logger.error(f"Unable to remove Instagram access token: {e}")
        raise RuntimeError("Unable to remove Instagram access token.") from e


def deauthorize_instagram_access_token(session: Session, ig_user_id: str) -> None:
    """
    Remove both project and user secrets using the user secret key
    """
    if not ig_user_id:
        raise ValueError("Instagram user ID is required.")

    user_secret_key = _ig_user_id_to_ig_project_name_key(ig_user_id)

    try:
        project_secret_key = secret.get_client_secret(user_secret_key)
    except KeyError as e:
        # if the key does not exist, then the project is not connected
        logger.error(e)
        return
    except Exception as e:
        logger.error(f"Unable to deauthorize Instagram access token: {e}")
        raise RuntimeError(f"Unable to deauthorize Instagram access token: {e}")

    try:
        # Remove both secrets
        secret.remove_client_secret(project_secret_key)

        # Temporary solution to try to avoid versioning errors
        time.sleep(5)

        try:
            secret.remove_client_secret(user_secret_key)
        except KeyError as e:
            # if the user_secret_key does not exist, log and continue
            logger.error(
                f"user secret {user_secret_key} does not exist, continuing: {e}"
            )
        except Exception as e:
            logger.error(f"Unable to remove user secret: {e}")
            raise RuntimeError("Unable to remove user secret.") from e
    except KeyError as e:
        # If the project_secret_key does not exist, check whether the user_secret_key exists
        logger.error(
            f"project secret does not exist, checking whether user secret exists: {e}"
        )

        try:
            # if user_secret_key exists, log data inconsistency
            secret.get_client_secret(user_secret_key)
        except KeyError as get_e:
            # Neither keys exists, so the project was already disconnected
            logger.error(
                f"Neither project secret nor user secret exist, continuing: {get_e}"
            )
            return
        except Exception as get_e:
            # Log error and raise
            logger.error(f"Unable to verify if user secret exists: {get_e}")
            raise RuntimeError("Unable to verify if user secret exists.") from get_e

        # if user_secret_key exists, log data inconsistency
        logger.error(
            "Inconsistent state, user secret exists but project secret does not."
        )
        raise RuntimeError(
            "Inconsistent state, user secret exists but project secret does not."
        )
    except Exception as e:
        logger.error(f"Unable to remove Instagram access token: {e}")
        raise RuntimeError("Unable to remove Instagram access token.") from e


def get_session_count_by_user_and_status(
    session: Session,
    user_ids: list[uuid.UUID],
    start_date: datetime,
    end_date: datetime,
    status: db.ConversationStatus | None = None,
) -> int:
    conversation_repository = db.ConversationRepository(session)
    return conversation_repository.get_session_count_by_user_and_status(
        user_ids=user_ids, start_date=start_date, end_date=end_date, status=status
    )


def get_escalated_session_count_by_users(
    session: Session,
    user_ids: list[uuid.UUID],
    start_date: datetime,
    end_date: datetime,
) -> int:
    conversation_repository = db.ConversationRepository(session)
    message_repository = db.MessageRepository(session)

    conversation_ids = conversation_repository.get_conversation_ids_by_user_ids(
        user_ids=user_ids,
        start_date=start_date,
        end_date=end_date,
        hide_testing_sessions=True,
    )

    escalated_conversation_count = message_repository.get_escalated_conversation_count(
        conversation_ids=conversation_ids, start_date=start_date, end_date=end_date
    )
    return escalated_conversation_count


def onboard_new_account(
    session: Session,
    context: UserContext,
    account_name: str,
    account_params: AccountParams,
    lead_id: uuid.UUID | None,
    agent_projects: list[tuple[AgentParams, list[ProjectSetup]]],
    users: list[CognitoUser] | None,
) -> list[CreatedProjectInfo]:
    # Collect project information to return
    created_projects: list[CreatedProjectInfo] = []

    try:
        # Create the account
        created_account = account_service.create_account(
            session=session,
            context=context,
            account_name=account_name,
            params=account_params,
            lead_id=lead_id,
            auto_commit=False,
        )

        for agent_project in agent_projects:
            agent_param = agent_project[0]
            project_setups = agent_project[1]
            agent = agent_service.create_agent(
                session=session,
                context=context,
                account_name=account_name,
                params=agent_param,
                auto_commit=False,
            )

            for project_setup in project_setups:
                # Set the agent id before creating project
                project_param = project_setup.params
                project_param.agent_id = agent.id

                # Add API channel with project name as identifier
                channels = project_param.channel_identifiers or []
                if project_setup.enable_web_widget:
                    channels.append(f"api:{project_param.name}")
                if channels:
                    project_param.channel_identifiers = channels

                # Create project
                project = project_service.create_project(
                    session=session,
                    context=context,
                    account_name=account_name,
                    project_name=project_param.name or "",
                    params=project_param,
                    auto_commit=False,
                )

                # Collect project information for response
                created_projects.append(
                    {
                        "project_id": str(project.id),
                        "project_name": project.name,
                        "agent_id": str(agent.id),
                        "enable_web_widget": project_setup.enable_web_widget,
                    }
                )

        # create cognito user accounts
        for user in users or []:
            create_account_user(account_name, user.email, user.name)

        # commit all changes at once.
        session.commit()
    except Exception as e:
        # Rollback the transaction if any error occurs
        session.rollback()
        logger.warn(f"Error creating resources for onboarding: {e}")
        raise ValueError(f"Failed to onboarding account. {e}")

    # Optionally create stripe customer
    _create_stripe_customer(session, context, created_account)

    # Phone number reservation is now handled separately via direct API calls
    return created_projects


def _create_stripe_customer(session, context, account: db.Account):
    try:
        if account and not account.stripe_customer_id:
            subscription_service.create_stripe_customer_for_account(
                session=session,
                context=context,
                account=account,
                customer_email=None,
            )
            logger.info(
                "Created Stripe customer during onboarding",
                extra={"account_name": account.name, "account_id": str(account.id)},
            )
    except Exception as e:
        logger.warning(
            f"Failed to create Stripe customer during onboarding: {e}",
            extra={"account_name": account.name, "account_id": str(account.id)},
        )


def upload_project_knowledge(
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
    """
    index_name, namespace = get_knowledge_settings(
        session, context, target, auto_create=True
    )
    _, existing_files = knowledge_service.list_knowledge_files(index_name, namespace)

    for file in existing_files:
        if file_name == file.name:
            logger.error(
                "File to upload already exist!",
                extra={
                    "file_name": file_name,
                    "files": existing_files,
                },
            )
            raise ValueError(
                "The file already exist in knowledge base, to update, first delete the file before uploading again."
            )
    return knowledge_service.upload_knowledge_file(
        index_name,
        namespace,
        file_name,
        content,
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
    This function gets the knowledge settings from the project's raw_config
    and uses them to query the Pinecone index for all files.

    Args:
        session: The database session
        target: The project or agent to retrieve knowledge files for
        filename: Optional filename to filter results by (case-insensitive partial match)
        offset: The number of files to skip
        limit: The maximum number of files to return

    Returns:
        tuple[int, list[dict]]: A tuple containing the total number of files and a list of file data
    """
    index_name, namespace = get_knowledge_settings(session, context, target)
    if not index_name or not namespace:
        logger.info(
            "Target has no knowledge setting, knowledge files not retrieved.",
            extra={
                "target_id": target.id,
                "target_type": type(target),
                "index_name": index_name,
                "namespace": namespace,
            },
        )
        return 0, []
    return knowledge_service.list_knowledge_files(
        index_name, namespace, filename, limit, offset
    )


def delete_knowledge_file(
    session: Session,
    context: UserContext,
    target: db.Project | db.Agent,
    filename: str,
) -> list[str]:
    index_name, namespace = get_knowledge_settings(session, context, target)
    return knowledge_service.delete_knowledge_file(index_name, namespace, filename)


def get_attr(attrs, key):
    return next((a["Value"] for a in attrs if a["Name"] == key), "")


def list_account_users(account_name: str) -> list[CognitoUser]:
    user_pool_id = AWS_ADMIN_CONSOLE_USER_POOL_ID
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    users = []
    pagination_token = None

    try:
        while True:
            # Unfortunately we can't search by custom attributes, therefore we
            # must first list all users, then manually filter by account name
            # to only return the users for this account.
            if pagination_token:
                response = cognito_client.list_users(
                    UserPoolId=user_pool_id,
                    PaginationToken=pagination_token,
                )
            else:
                response = cognito_client.list_users(
                    UserPoolId=user_pool_id,
                )

            fetched_users = response.get("Users", [])
            for user in fetched_users:
                attributes = user.get("Attributes")
                if not attributes:
                    logger.warn(
                        "User has no attributes!",
                        extra={"user_pool_id": user_pool_id, "user_data": user},
                    )
                    continue

                account = get_attr(attributes, "custom:account_name")
                if account != account_name:
                    continue

                email = get_attr(attributes, "email")
                name = get_attr(attributes, "name")
                status = user.get("UserStatus")

                users.append(CognitoUser(email=email, name=name, status=status))

            pagination_token = response.get("PaginationToken")
            if not pagination_token or not fetched_users:
                break
        return users
    except ClientError as e:
        logger.error(f"Error listing Cognito users: {e}")
        raise ValueError(f"Failed to list Cognito users: {str(e)}")


CREATE_USER_TEMPLATE_ID = 40701112


def create_account_user(
    account_name: str,
    user_email: str,
    user_name: str,
) -> CognitoUser:
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    password = generate_password()
    try:
        cognito_client.admin_create_user(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Username=user_email,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": user_email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": user_name},
                {"Name": "custom:account_name", "Value": account_name},
            ],
        )
        logger.info(f"Created user account for {user_email} using AdminCreateUser")
        try:
            email_service.send_email_with_template(
                to_email=user_email,
                template_id=CREATE_USER_TEMPLATE_ID,
                template_model={
                    "name": user_name,
                    "email": user_email,
                    "account_name": account_name,
                    "product_name": "Palona AI",
                    "password": password,
                    "login_url": (
                        (
                            "https://console.palona.ai"
                            if os.getenv("RUNTIME_ENV", "prd") == "prd"
                            else f"https://{os.getenv('RUNTIME_ENV','lat')}-console.palona.ai"
                        )
                        + f"/signin?email={user_email}"
                    ),
                    "sender_name": "Support Team",
                },
            )
            logger.info(f"Welcome email sent to {user_email}")
        except Exception as e:
            logger.error(f"Failed to send welcome email via Postmark: {e}")
        return CognitoUser(
            email=user_email,
            name=user_name,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "UsernameExistsException":
            logger.error(f"User with email {user_email} already exists: {e}")
            raise ValueError(f"User with email {user_email} already exists") from e
        else:
            logger.error(f"Error creating Cognito user: {e}")
            raise ValueError(
                f"Failed to create Cognito user account for {user_email}: {e}"
            ) from e


def signup_account_user(
    account_name: str,
    user_email: str,
    user_name: str,
    password: str,
) -> CognitoUser:
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    try:
        # Step 1: Sign up the user
        signup_response = cognito_client.sign_up(
            ClientId=AWS_ADMIN_CONSOLE_APP_CLIENT_ID,
            Username=user_email,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": user_email},
                {"Name": "name", "Value": user_name},
                {"Name": "custom:account_name", "Value": account_name},
            ],
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "UsernameExistsException":
            logger.error(f"User with email {user_email} already exists: {e}")
            raise ValueError(f"User with email {user_email} already exists") from e
        elif error_code == "InvalidPasswordException":
            logger.error(f"Invalid password for user {user_email}: {e}")
            raise ValueError(e.response["Error"]["Message"]) from e
        else:
            logger.error(str(e))
            raise ValueError(
                f"Failed to create Cognito user account for {user_email}"
            ) from e

    try:
        user_sub = signup_response["UserSub"]
        # Step 2: Confirm user
        cognito_client.admin_confirm_sign_up(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID, Username=user_email
        )
        # Step 3: Authenticate to get session tokens
        auth_response = cognito_client.admin_initiate_auth(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            ClientId=AWS_ADMIN_CONSOLE_APP_CLIENT_ID,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": user_email,
                "PASSWORD": password,
            },
        )
        id_token = auth_response["AuthenticationResult"]["IdToken"]
        access_token = auth_response["AuthenticationResult"]["AccessToken"]
        refresh_token = auth_response["AuthenticationResult"]["RefreshToken"]
        expires_in = auth_response["AuthenticationResult"]["ExpiresIn"]
        # ADD EMAIL SENDING HERE

        # TODO: Add email verification here
        # email = email_service.send_email_with_template()

        return CognitoUser(
            email=user_email,
            name=user_name,
            session=CognitoUserSession(
                user_sub=user_sub,
                id_token=id_token,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            ),
        )
    except Exception as e:
        logger.error(
            f"SIGNUP: Error auto-confirming and authenticating Cognito user: {e}"
        )
        raise ValueError(f"Failed to obtain user session for user {user_email}") from e


def signup_self_onboarding_user(
    account_name: str,  # not used here; map user->account in your DB
    user_email: str,
    user_name: str,
    password: str,
    is_google_user: bool = False,
) -> CognitoUser:
    """
    Creates (or reuses) a Cognito user without sending email and sets a permanent password.
    Returns True if the user is ready to sign in; raises on real errors.
    """
    cognito = boto3.client("cognito-idp", region_name=AWS_REGION)

    # 1) Try to create user (suppress invite)
    try:
        if is_google_user:
            # Google users are already verified by Google, so we can set email_verified to true
            cognito.admin_create_user(
                UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
                Username=user_email,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": user_email},
                    {"Name": "name", "Value": user_name},
                    {"Name": "custom:is_google_user", "Value": "true"},
                    {"Name": "custom:account_name", "Value": account_name},
                ],
            )
        else:
            cognito.admin_create_user(
                UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
                Username=user_email,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": user_email},
                    # Only set email_verified if you truly verified it out-of-band:
                    # {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": user_name},
                    {"Name": "custom:account_name", "Value": account_name},
                ],
            )

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "UsernameExistsException":
            # Idempotent: user already exists; continue to set permanent password
            logger.info(
                f"[Cognito] User {user_email} already exists; ensuring permanent password."
            )
            raise ValueError(f"User {user_email} already exists") from e
        else:
            logger.error(f"[Cognito] admin_create_user failed for {user_email}: {e}")
            raise ValueError(
                f"Failed to create Cognito user for {user_email}: {e}"
            ) from e

    # 2) Set permanent password so client can sign in immediately
    try:
        cognito.admin_set_user_password(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Username=user_email,
            Password=password,
            Permanent=True,
        )
    except ClientError as e:
        logger.error(f"[Cognito] admin_set_user_password failed for {user_email}: {e}")
        raise ValueError(
            f"Failed to set permanent password for {user_email}: {e}"
        ) from e
    try:
        auth_response = cognito.admin_initiate_auth(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            ClientId=AWS_ADMIN_CONSOLE_APP_CLIENT_ID,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": user_email,
                "PASSWORD": password,  # Same password that was just set
            },
        )
    except ClientError as e:
        logger.error(f"[Cognito] admin_initiate_auth failed for {user_email}: {e}")
        raise ValueError(
            f"Failed to authenticate Cognito user for {user_email}: {e}"
        ) from e
    try:
        user_response = cognito.admin_get_user(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID, Username=user_email
        )
        user_sub = None
        for attr in user_response["UserAttributes"]:
            if attr["Name"] == "sub":
                user_sub = attr["Value"]
                break
        if not user_sub:
            raise ValueError(f"User sub not found for {user_email}")
    except ClientError as e:
        logger.error(f"[Cognito] admin_get_user failed for {user_email}: {e}")
        raise ValueError(f"Failed to get Cognito user for {user_email}: {e}") from e

    # Extract tokens
    id_token = auth_response["AuthenticationResult"]["IdToken"]
    access_token = auth_response["AuthenticationResult"]["AccessToken"]
    refresh_token = auth_response["AuthenticationResult"]["RefreshToken"]
    expires_in = auth_response["AuthenticationResult"]["ExpiresIn"]

    return CognitoUser(
        email=user_email,
        name=user_name,
        session=CognitoUserSession(
            user_sub=user_sub,
            id_token=id_token,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        ),
    )


def check_user_exists(email: str) -> bool:
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    try:
        response = cognito_client.list_users(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Filter=f'email="{email}"',
        )
        users = response.get("Users", [])
        return len(users) > 0
    except ClientError as e:
        logger.error(f"Error checking if user exists: {e}")
        return False


def verify_and_decode_google_credential(google_credential: str) -> dict:
    try:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": google_credential},
            timeout=10,
        )
        if response.status_code != 200:
            raise ValueError("Invalid Google token")
        payload = response.json()
        if payload.get("aud") != os.environ.get("GOOGLE_CLIENT_ID"):
            raise ValueError("Token is for another application")
        if int(payload.get("exp", 0)) < int(datetime.now().timestamp()):
            raise ValueError("Token has expired")
        if payload.get("iss") not in [
            "accounts.google.com",
            "https://accounts.google.com",
        ]:
            raise ValueError("Invalid token issuer")
        if not payload.get("email_verified", False):
            raise ValueError("Email not verified by Google")
        return {
            "email": payload.get("email"),
            "name": payload.get("name"),
        }
    except requests.RequestException as e:
        raise ValueError(f"Failed to verify Google token: {e}") from e
    except (KeyError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid token format: {str(e)}")


def signup_google_onboarding_user(
    account_name: str, google_credential: str
) -> CognitoUser:
    try:
        user_info = verify_and_decode_google_credential(google_credential)
        email = user_info["email"]
        name = user_info["name"]
        # Generate a random secure password since Google users won't use it
        password = os.getenv("GOOGLE_SHARED_PASSWORD", "")
        if check_user_exists(user_info.get("email", "")):
            raise ValueError("User with this email already exists")
        return signup_self_onboarding_user(
            account_name=account_name,
            user_email=email,
            user_name=name,
            password=password,
            is_google_user=True,
        )
    except ValueError as e:
        raise ValueError(f"Google credential verification failed: {e}") from e


def signin_google_user(google_credential: str):
    try:
        user_info = verify_and_decode_google_credential(google_credential)
        cognito = boto3.client("cognito-idp", region_name=AWS_REGION)
        email = user_info["email"]
        password = os.getenv("GOOGLE_SHARED_PASSWORD", "")

        try:
            response = cognito.admin_initiate_auth(
                UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
                ClientId=AWS_ADMIN_CONSOLE_APP_CLIENT_ID,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": email,
                    "PASSWORD": password,  # Same password that was just set
                },
            )

            if "AuthenticationResult" in response:
                return {
                    "is_signed_in": True,
                    "next_step": "DONE",
                    "tokens": {
                        "id_token": response["AuthenticationResult"]["IdToken"],
                        "access_token": response["AuthenticationResult"]["AccessToken"],
                        "refresh_token": response["AuthenticationResult"][
                            "RefreshToken"
                        ],
                    },
                }
            elif "ChallengeName" in response:
                challenge_name = response["ChallengeName"]
                if challenge_name == "NEW_PASSWORD_REQUIRED":
                    return {
                        "is_signed_in": False,
                        "next_step": "NEW_PASSWORD_REQUIRED",
                        "session": response.get("Session"),
                    }
                return {
                    "is_signed_in": False,
                    "next_step": "UNKNOWN",
                    "session": response.get("Session"),
                }
        except ClientError as e:
            logger.error(f"[Cognito] admin_initiate_auth failed for {email}: {e}")
            raise ValueError(
                f"Failed to authenticate Cognito user for {email}: {e}"
            ) from e
    except ValueError as e:
        raise ValueError(f"Google Authentication Failed: {e}") from e


def is_google_user(email: str) -> bool:
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    try:
        response = cognito_client.list_users(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Filter=f'email="{email}"',
        )
        users = response.get("Users", [])
        if not users:
            raise ValueError(f"User not found for email: {email}")

        user = users[0]
        is_google_user = get_attr(user.get("Attributes", []), "custom:is_google_user")
        return is_google_user.lower() == "true"
    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            logger.error(f"User {email} not found: {e}")
            raise ValueError(f"User {email} not found")
        else:
            logger.error(f"Error checking if user is Google user: {e}")
            raise ValueError(f"Failed to check if user is Google user: {str(e)}")


def delete_account_user(account_name: str, user_email: str) -> None:
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    try:
        response = cognito_client.list_users(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Filter=f'email="{user_email}"',
        )
        users = response.get("Users", [])
        if not users:
            raise ValueError(f"User not found for email: {user_email}")

        user = users[0]
        user_account_name = get_attr(user.get("Attributes", []), "custom:account_name")

        if user_account_name != account_name:
            logger.error(f"User {user_email} not found in account {account_name}")
            raise ValueError(f"User {user_email} not found in account {account_name}")

        cognito_client.admin_delete_user(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Username=user_email,
        )

        logger.info(f"Deleted cognito user from account {account_name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            logger.error(f"User {user_email} not found: {e}")
            raise ValueError(f"User {user_email} not found")
        else:
            logger.error(f"Error deleting Cognito user: {e}")
            raise ValueError(f"Failed to delete Cognito user: {str(e)}")


def get_user_account_names(user_email: str) -> list[str]:
    """
    Get the account_names attribute for a Cognito user.

    This function retrieves the custom:account_names attribute from Cognito
    and returns it as a list of account names.

    Args:
        user_email: The email address of the user to retrieve account names for

    Returns:
        list[str]: List of account names associated with the user

    Raises:
        ValueError: If user not found
    """
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)

    try:
        # Find the user by email
        response = cognito_client.list_users(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Filter=f'email="{user_email}"',
        )
        users = response.get("Users", [])
        if not users:
            raise ValueError(f"User not found for email: {user_email}")

        user = users[0]
        attributes = user.get("Attributes", [])

        # Get the custom:account_names attribute
        account_names_str = get_attr(attributes, "custom:account_names")

        if not account_names_str:
            return []

        account_names = [
            name.strip() for name in account_names_str.split(",") if name.strip()
        ]

        logger.info(
            f"Retrieved account_names for user (count: {len(account_names)} accounts)"
        )
        return account_names

    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            logger.error(f"User not found: {e}")
            raise ValueError(f"User not found for email: {user_email}") from e
        else:
            logger.error(f"Error retrieving user account_names: {e}")
            raise ValueError(
                f"Failed to retrieve account_names for user: {str(e)}"
            ) from e


def update_user_account_names(
    user_email: str,
    account_names: list[str],
) -> None:
    """
    Update the account_names attribute for a Cognito user.

    This function updates the custom:account_names attribute in Cognito with
    a comma-separated list of account names. This allows users to have access
    to multiple accounts.

    Args:
        user_email: The email address of the user to update
        account_names: List of account names to associate with the user

    Raises:
        ValueError: If user not found or update fails
    """
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)

    if not account_names:
        raise ValueError("account_names list cannot be empty")

    account_names_str = ",".join(account_names)

    try:
        # Verify the user exists
        response = cognito_client.list_users(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Filter=f'email="{user_email}"',
        )
        users = response.get("Users", [])
        if not users:
            raise ValueError(f"User not found for email: {user_email}")

        user = users[0]
        username = user.get("Username")

        # Update the custom:account_names attribute
        cognito_client.admin_update_user_attributes(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Username=username,
            UserAttributes=[
                {
                    "Name": "custom:account_names",
                    "Value": account_names_str,
                }
            ],
        )

        logger.info(
            f"Updated account_names for user {user_email} to: {account_names_str}"
        )

    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            logger.error(f"User {user_email} not found: {e}")
            raise ValueError(f"User {user_email} not found") from e
        else:
            logger.error(f"Error updating user account_names: {e}")
            raise ValueError(
                f"Failed to update account_names for {user_email}: {str(e)}"
            ) from e


def get_user_name_by_email(email: str) -> str | None:
    """
    Retrieves the user's display name from AWS Cognito by email address.

    Args:
        email: The email address of the user

    Returns:
        The user's display name (from the 'name' attribute) or None if not found
    """
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
    try:
        response = cognito_client.list_users(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID,
            Filter=f'email="{email}"',
        )
        users = response.get("Users", [])
        if not users:
            logger.warning(f"No user found for email: {email}")
            return None

        user = users[0]
        name = get_attr(user.get("Attributes", []), "name")
        return name if name else None
    except ClientError as e:
        logger.error(f"Error retrieving user name for email {email}: {e}")
        return None


def update_conversation(
    session: Session,
    conversation_id: uuid.UUID,
    is_escalated: bool | None,
    project_id: uuid.UUID | None,
) -> db.Conversation | None:
    conversation_repository = db.ConversationRepository(session)
    update_data = ConversationUpdate(
        is_escalated=is_escalated,
        project_id=project_id,
    )
    return conversation_repository.update_conversation(
        conversation_id=conversation_id, update_data=update_data
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
    try:
        lead_repo = db.LeadRepository(session)

        # Convert service filter to repository filter
        repo_filter = RepoLeadFilter(
            page=filter_params.page,
            page_size=filter_params.page_size,
            status_filter=filter_params.status_filter,
            segment_filter=filter_params.segment_filter,
            tier_filter=filter_params.tier_filter,
            keyword=filter_params.keyword,
        )

        leads, total_count = lead_repo.list_leads_paginated(repo_filter)

        return leads, total_count

    except Exception as e:
        logger.error(f"Error listing leads: {e}")
        raise


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
    try:
        if not params.business_name:
            raise ValueError("business_name is required for creating a lead")

        lead_repo = db.LeadRepository(session)

        lead = lead_repo.create_lead(
            business_name=params.business_name,
            business_address=params.business_address,
            logo_uri=params.logo_uri,
            segment=params.segment,
            tier=params.tier,
            owner=params.owner,
            hubspot_record_id=params.hubspot_record_id,
            status=params.status,
            notes=params.notes,
            pos=params.pos,
            channels=params.channels,
            contract_signed=params.contract_signed,
        )

        logger.info(
            f"Created lead: {lead.id} for business: {params.business_name}",
            extra={
                "lead_id": str(lead.id),
                "business_name": params.business_name,
                "created_by": context.email,
            },
        )
        return lead
    except Exception as e:
        logger.error(f"Error creating lead: {e}")
        raise


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
    try:
        lead_repo = db.LeadRepository(session)

        param_dict = asdict(params)
        lead = lead_repo.update_lead(lead_id, **param_dict)
        if lead:
            logger.info(
                f"Updated lead: {lead.id}",
                extra={
                    "lead_id": str(lead.id),
                    "updated_by": context.email,
                    "fields": param_dict,
                },
            )
        return lead
    except Exception as e:
        logger.error(f"Error updating lead: {e}")
        raise


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
    lead_repo = db.LeadRepository(session)

    lead_repo.delete_lead(lead_id)
    logger.info(
        f"Deleted lead: {lead_id}",
        extra={
            "lead_id": str(lead_id),
            "deleted_by": context.email,
        },
    )


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
    lead_repo = db.LeadRepository(session)
    lead = lead_repo.get_lead_by_id(lead_id)
    return lead


## Brand Scraper
class JsonSchema(BaseModel):
    company_description: str


def get_brand_extract_prompt() -> str:
    return """
    Extract a concise company description from the given webpage text. 
    The description should summarize:
    - What the company does (products/services)
    - The industry or sector it operates in
    - Who its customers or target audience are (if mentioned)
    - Any unique value proposition, mission, or vision
    - What food or items the company sells and are known for

    Write the description in 2–5 clear professional sentences. 
    Do not include irrelevant information, navigation text, or job postings. 
    If no description can be found, respond with: "No clear company description found."
    """


def scrape_brand_from_url(url: str):
    """
    Scrape a description of the brand from a URL using Firecrawl.
    """
    ## Set up Firecrawl
    try:
        api_key = get_client_secret_with_fallback("FIRECRAWL_API_KEY")
    except ValueError as e:
        raise ValueError("Firecrawl API key required.") from e
    firecrawl = Firecrawl(api_key=api_key)

    ## Firecrawl Map
    mappedPage = None
    search_queries = ["about", "story", "overview", "home"]

    for search_query in search_queries:
        res = firecrawl.map(url=url, limit=50, sitemap="include", search=search_query)
        if res:
            mappedPage = res
            break

    ## Firecrawl Scrape
    if mappedPage and hasattr(mappedPage, "links") and mappedPage.links:
        links = mappedPage.links
        if links:
            for link in links:
                if "xml" not in link.url:
                    res = firecrawl.scrape(
                        link.url,
                        formats=[
                            {
                                "type": "json",
                                "schema": JsonSchema,
                                "prompt": get_brand_extract_prompt(),
                            }
                        ],
                        only_main_content=False,
                        timeout=120000,
                        proxy="auto",
                    )
                    if res and res.json and res.json.get("company_description"):
                        return res.json["company_description"]
    return ""
