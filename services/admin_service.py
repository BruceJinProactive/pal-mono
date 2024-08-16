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
    project = project_repository.create_project(account_id=account.id)
    _ = assistant_repository.create_assistant(project_id=project.id)

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
