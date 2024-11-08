from typing import List, Optional

from sqlalchemy.orm import Session

from db.repositories.account_repository import AccountRepository
from db.repositories.assistant_repository import AssistantRepository
from db.repositories.project_repository import ProjectRepository
from db.tables import Account


def get_accounts(db: Session) -> List[Account]:
    account_repository = AccountRepository(db)
    accounts = account_repository.get_accounts()
    return accounts


def get_account(db: Session, account_name: str) -> Optional[Account]:
    account_repository = AccountRepository(db)
    account = account_repository.get_account(account_name=account_name)
    return account


def create_account_with_defaults(db: Session, account_name: str) -> Account:
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
