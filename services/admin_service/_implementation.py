import uuid
from typing import List

from sqlalchemy.orm import Session

from api.models.conversation import ConversationPreview
from db.repositories.conversation_repository import ConversationRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.user_repository import UserRepository
from db.tables.messages import Message
from services.account_service import get_account
from services.assistant_service import get_assistants_by_account
from services.message_service import (
    get_conversations_by_users,
    get_messages_by_conversation,
)
from services.user_service import get_users_by_account_id


def get_inbox_conversations(
    db: Session, account_id: uuid.UUID
) -> List[ConversationPreview]:
    # Get users associated with the account
    users = get_users_by_account_id(db, account_id=account_id)

    # Get all conversations involving a user with the account id
    conversations = get_conversations_by_users(
        db, user_ids=list(map(lambda user: user.id, users))
    )
    conversation_user_ids = list(
        map(lambda conv: (conv.id, conv.user_id), conversations)
    )

    message_counts: List[int] = []
    last_messages: List[Message] = []

    message_repository = MessageRepository(db)
    for id, _ in conversation_user_ids:
        # Get most recent message for each conversation
        last_messages.append(message_repository.get_last_message_by_conversation(id))

        # Get most number of messages for each conversation
        message_counts.append(message_repository.get_message_count_by_conversation(id))

    # filter conversations by those with at least one message, and sorted descending by created_at
    conversation_previews = sorted(
        filter(
            lambda preview: preview[3],
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

    # Reformat conversations
    inbox: List[ConversationPreview] = [
        ConversationPreview(
            id=str(conversation[0]),
            user_id=str(conversation[1]),
            num_messages=conversation[2],
            last_message_text=(
                conversation[3].body.get("text", {}).get("body", "")
                if conversation[3].body is not None
                else ""
            ),
        )
        for conversation in conversation_previews
    ]

    return inbox


def get_conversation_messages(
    db: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
) -> List[Message]:
    conversation_repository = ConversationRepository(db)
    user_repository = UserRepository(db)

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
    messages = get_messages_by_conversation(db, conversation_id=conversation_id)

    return messages


def get_brandings(db: Session, account_name: str) -> list[dict]:
    account = get_account(db, account_name)

    account_name = account.name
    assistants = get_assistants_by_account(db, account_name)

    # # find the assistant's raw config
    # parse the raw config with the branding key
    # error check, if it doesn't have the branding key, send back an empty json
    brandings = []
    for assistant in assistants:
        if "branding" in assistant.raw_config:
            branding = assistant.raw_config.get("branding", {})
            brandings.append(branding)
    return brandings
