import uuid
from typing import List

from phi.assistant.run import AssistantRun
from phi.storage.assistant.postgres import PgAssistantStorage
from sqlalchemy.orm import Session

from db.repositories.conversation_repository import ConversationRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.user_repository import UserRepository
from db.settings import db_settings
from db.tables.messages import Message
from services.account_service import get_account
from services.conversation_service import get_conversations_by_users
from services.message_service.message_service import get_messages_by_conversation
from services.user_service import get_users_by_account


class Row:
    def __init__(self, run: AssistantRun):
        memory_json = run.memory
        self.user_id = memory_json.get("user_id")
        self.created_at = run.created_at
        self.memories = memory_json.get("memories")
        self.chat_history = memory_json.get("chat_history")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "memories": str(self.memories),
            "chat_history": len(self.chat_history),
        }


def get_assistant_data(db: Session, account_name: str):
    account = get_account(db, account_name=account_name)
    if account is None:
        raise ValueError("Account not found")
    if not account.projects:
        raise ValueError("No projects found for this account")
    project_id = account.projects[0].id
    storage_table_name = f"project_{project_id}_storage"
    storage = PgAssistantStorage(
        table_name=storage_table_name,
        db_url=db_settings.get_db_url(),
    )
    all_runs = storage.get_all_runs()
    rows = []
    for run in all_runs:
        rows.append(run)
    return rows


def get_inbox_conversations(
    db: Session, account_id: uuid.UUID
) -> List[tuple[uuid.UUID, uuid.UUID, int, Message]]:
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

    # return conversations filtered by those with at least one message, and sorted by created_at
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
    return conversation_previews


def get_conversation_messages(
    db: Session, account_id: uuid.UUID, conversation_id: uuid.UUID
):
    conversation_repository = ConversationRepository(db)
    user_repository = UserRepository(db)

    """
    First ensure that the requesting account can access this conversation
    """

    conversation = conversation_repository.get_conversation_by_id(conversation_id)

    if not conversation:
        raise ValueError(f"No conversation with id {conversation_id}")

    user = user_repository.get_user_by_id(conversation.user_id)

    if not user:
        raise ValueError(f"No user with id {conversation.user_id}")

    if user.account_id != account_id:
        raise Exception(">:(")

    # Requesting account matches account associated with conversation

    # Get messages and return
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
