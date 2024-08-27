from phi.assistant.run import AssistantRun
from phi.storage.assistant.postgres import PgAssistantStorage
from sqlalchemy.orm import Session

from db.repositories.account_repository import AccountRepository
from db.repositories.assistant_repository import AssistantRepository
from db.repositories.project_repository import ProjectRepository
from db.settings import db_settings


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


def get_account(db: Session, account_name: str):
    account_repository = AccountRepository(db)
    account = account_repository.get_account(account_name=account_name)
    return account


def create_account_with_defaults(db: Session, account_name: str):
    # Instantiate the repositories
    account_repository = AccountRepository(db)
    project_repository = ProjectRepository(db)
    assistant_repository = AssistantRepository(db)

    # Use the repositories to create the account, project, and assistant
    account = account_repository.create_account(account_name)
    assistant = assistant_repository.create_assistant(account_id=account.id)
    project_repository.create_project(
        project_name=f"{account_name}-default",
        account_id=account.id,
        assistant_id=assistant.id,
    )

    return account


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


def get_inbox_messages():
    """This is a placeholder implementation"""
    chat_data = [
        {
            "chatId": 36478232,
            "lastMessage": "A professional dreads deadlines",
            "numMessages": 85,
        },
        {
            "chatId": 47593205,
            "lastMessage": "A parent proud at graduation",
            "numMessages": 164,
        },
        {
            "chatId": 75892945,
            "lastMessage": "An artist inspired by sunset",
            "numMessages": 1100,
        },
        {
            "chatId": 46284652,
            "lastMessage": "A teacher satisfied by a lesson",
            "numMessages": 19,
        },
        {
            "chatId": 18402851,
            "lastMessage": "A pet owner saddened by loss",
            "numMessages": 436,
        },
    ]
    return chat_data


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
