import uuid
from typing import List

from sqlalchemy.orm import Session

from api.models.conversation import ConversationPreview
from db.repositories.conversation_repository import ConversationRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.user_repository import UserRepository
from db.tables.messages import Message
from services.conversation_service import get_conversations_by_users
from services.message_service import get_messages_by_conversation
from services.user_service import get_users_by_account


def get_inbox_conversations(
    db: Session, account_id: uuid.UUID
) -> List[ConversationPreview]:
    """
    Retrieves a list of conversation previews for all conversations associated with the given account.

    The function first fetches all users associated with the specified Account ID. It then retrieves
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

    # Get users associated with the account
    users = get_users_by_account(db, account_id=account_id)

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
):
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


def get_knowledge_base():
    knowledge_base_json = {
        "profile": {
            "company": "Proactive AI Lab",
            "email": "agent@proactiveailab.com",
            "phone": "555-555-5555",
            "website": "https://www.proactiveailab.com",
        },
        "branding": "Our AI agent is designed to emulate a real person, utilizing a new generation of AI systems with multi-agents and multimodal-to-action models, enhancing its high EQ language capabilities.",
        "prompt": "You're name is Anna and you are a highly emotionally intelligent executive assistant.\n\n - You have expertise in coding.\n - You have expertise in customer service.\n - You have expertise in sales and marketing.",
        "terms_&_faq": "Once upon a time, in a bustling tech hub, a team of passionate innovators embarked on a remarkable journey to revolutionize customer interactions. Their vision? To create an advanced AI system equipped with multi-agents and multimodal-to-action models, complemented by a cutting-edge high EQ language model. With unwavering determination, they set out to empower businesses worldwide, enabling them to provide unparalleled levels of personalized customer experiences, seamless automation, and unmatched operational efficiency. This is the inspiring founder story behind the groundbreaking technology that is reshaping the future of customer engagement.",
    }
    return knowledge_base_json
