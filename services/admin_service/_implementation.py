import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

import db
from api.schemas.admin.conversation import ConversationPreview
from services.account_service import get_account
from services.agent_service import get_agents_by_account
from services.message_service import (
    get_conversations_by_users,
    get_messages_by_conversation,
)
from services.project_service import get_project
from services.user_service import get_users_by_account_id
from utils import secret
from utils.log import logger


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


def get_inbox_conversations(
    session: Session, account_id: uuid.UUID, max_age: int
) -> List[ConversationPreview]:
    # Get users associated with the account
    users = get_users_by_account_id(session, account_id=account_id)

    # Get all conversations involving a user with the account id
    conversations = get_conversations_by_users(
        session, user_ids=list(map(lambda user: user.id, users))
    )
    conversation_user_ids = list(
        map(lambda conv: (conv.id, conv.user_id), conversations)
    )

    message_counts: List[int] = []
    last_messages: List[db.Message] = []

    message_repository = db.MessageRepository(session)
    for id, _ in conversation_user_ids:
        # Get most recent message for each conversation
        last_message = message_repository.get_last_message_by_conversation(id)

        # If there are no messages, skip this conversation
        if last_message is None:
            continue

        # If the last message is from datadog, skip this conversation
        if last_message.body.get("sender_identifier", "") == "datadog":
            continue

        last_messages.append(last_message)

        # Get most number of messages for each conversation
        message_counts.append(message_repository.get_message_count_by_conversation(id))

    # filter conversations by recency of last message, and sort descending by created_at
    conversation_previews = sorted(
        filter(
            lambda preview: _include_conversation_preview(preview[3], max_age),
            zip(
                [id for id, _ in conversation_user_ids],  # conversation IDs
                [user_id for _, user_id in conversation_user_ids],  # user IDs,
                message_counts,
                last_messages,
            ),
        ),
        key=lambda preview: preview[3].created_at,
        reverse=True,
    )

    def _get_last_message_text(message: db.Message) -> str:
        if message.body.get("text") is not None:
            return message.body.get("text", {}).get("body", "")
        elif message.body.get("media") is not None:
            return message.body.get("media", {}).get("url", "")
        return ""

    # Reformat conversations
    inbox: List[ConversationPreview] = [
        ConversationPreview(
            id=str(conversation[0]),
            user_id=str(conversation[1]),
            num_messages=conversation[2],
            last_message_text=_get_last_message_text(conversation[3]),
        )
        for conversation in conversation_previews
    ]

    return inbox


def get_conversation_messages(
    session: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> List[db.Message]:
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
            m if isinstance(m, str) else m.body.get("timestamp", datetime.min),
        ),
    )

    return messages


def get_messages_by_conversation_id(
    session: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> List[db.Message]:
    conversation_repository = db.ConversationRepository(session)
    user_repository = db.UserRepository(session)
    feedback_repository = db.FeedbackRepository(session)

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

    messages = get_messages_by_conversation(session, conversation_id=conversation_id)

    message_ids = [message.id for message in messages]
    feedback_for_messages = feedback_repository.get_feedback_by_message_ids(message_ids)

    message_id_to_feedback = defaultdict(list)
    for feedback in feedback_for_messages:
        message_id_to_feedback[feedback.message_id].append(feedback)

    for message in messages:
        message.feedback = message_id_to_feedback[message.id]

    return messages


def get_brandings(session: Session, account_name: str) -> list[dict]:
    account = get_account(session, account_name)
    if not account:
        return []
    account_name = account.name
    agents = get_agents_by_account(session, account_name)
    if not agents:
        return []
    # # find the agent's raw config
    # parse the raw config with the branding key
    # error check, if it doesn't have the branding key, send back an empty json
    brandings = []
    for agent in agents:
        if "branding" in agent.raw_config:
            branding = agent.raw_config.get("branding", {})
            brandings.append(branding)
    return brandings


def _project_name_to_ig_access_token_key(project_name: str) -> str:
    return f"{project_name.upper()}_INSTAGRAM_ACCESS_TOKEN"


def get_instagram_connected(session: Session, project_id: uuid.UUID) -> bool:
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    secret_tag_key = _project_name_to_ig_access_token_key(project.name)
    try:
        # if successful, then the key exists, and hence the project is connected
        secret.get_client_secret(secret_tag_key)
        return True
    except KeyError:
        # if the key does not exist, then the project is not connected
        return False
    except Exception as e:
        # if any other error occurs, log and raise
        logger.info(f"Unable to get Instagram access token: {e}")
        raise RuntimeError(f"Unable to get Instagram access token: {e}")


def set_instagram_access_token(
    session: Session, project_id: uuid.UUID, access_token: str
) -> None:
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    secret_tag_key = _project_name_to_ig_access_token_key(project.name)
    try:
        secret.add_client_secret(secret_tag_key, access_token)
    except KeyError as e:
        # if the key already exists, then the project is already connected
        logger.info(e)
    except Exception as e:
        logger.error(f"Unable to set Instagram access token: {e}")
        raise RuntimeError(f"Unable to set Instagram access token: {e}")


def remove_instagram_access_token(session: Session, project_id: uuid.UUID) -> None:
    project = get_project(session, project_id)
    if not project:
        raise ValueError("Project not found.")

    secret_tag_key = _project_name_to_ig_access_token_key(project.name)
    try:
        secret.remove_client_secret(secret_tag_key)
    except KeyError as e:
        # if the key does not exist, then the project is not connected
        logger.info(e)
    except Exception as e:
        logger.error(f"Unable to remove Instagram access token: {e}")
        raise RuntimeError(f"Unable to remove Instagram access token: {e}")
