from typing import List, Optional

from sqlalchemy.orm import Session

import db


def get_accounts(session: Session) -> List[db.Account]:
    account_repository = db.AccountRepository(session)
    accounts = account_repository.get_accounts()
    return accounts


def get_account(session: Session, account_name: str) -> Optional[db.Account]:
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name=account_name)
    return account


def create_account_with_defaults(session: Session, account_name: str) -> db.Account:
    # Instantiate the repositories
    account_repository = db.AccountRepository(session)
    project_repository = db.ProjectRepository(session)
    agent_repository = db.AgentRepository(session)

    # Use the repositories to create the account, project, and agent
    account = account_repository.create_account(account_name)
    agent = agent_repository.create_agent(account_id=account.id)
    project_repository.create_project(
        project_name=f"{account_name}-default",
        account_id=account.id,
        agent_id=agent.id,
    )
    return account
