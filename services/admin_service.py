from sqlalchemy.orm import Session

from db.repositories.account_repository import AccountRepository
from db.repositories.assistant_repository import AssistantRepository
from db.repositories.project_repository import ProjectRepository


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
