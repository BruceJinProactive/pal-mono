from dataclasses import asdict
from typing import List, Optional

from ddtrace import tracer
from sqlalchemy.orm import Session

import db
from services.account_service.schema import AccountParams


@tracer.wrap()
def get_accounts(session: Session) -> List[db.Account]:
    account_repository = db.AccountRepository(session)
    accounts = account_repository.get_accounts()
    return accounts


@tracer.wrap()
def get_account(session: Session, account_name: str) -> Optional[db.Account]:
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name=account_name)
    return account


@tracer.wrap()
def mget_accounts(session: Session, account_names: List[str]) -> List[db.Account]:
    account_repository = db.AccountRepository(session)
    accounts = account_repository.get_accounts_by_names(account_names)
    return accounts


@tracer.wrap()
def filter_accounts_by_name(
    session: Session,
    keyword: Optional[str] = None,
    limit: int = 20,
) -> List[db.Account]:
    """
    Filter accounts by a flexible name match using a keyword.
    Returns a limited number of results (default 20) to prevent returning too much data.
    """
    account_repository = db.AccountRepository(session)
    accounts = account_repository.filter_accounts_by_name(keyword, limit)
    return accounts


@tracer.wrap()
def create_account_with_defaults(session: Session, account_name: str) -> db.Account:
    # Instantiate the repositories
    account_repository = db.AccountRepository(session)
    project_repository = db.ProjectRepository(session)
    agent_repository = db.AgentRepository(session)

    # Use the repositories to create the account, project, and agent
    account = account_repository.create_account(account_name)
    agent = agent_repository.create_agent(account_id=account.id)
    project_repository.create_project(
        account.id,
        f"{account_name}-default",
        agent_id=agent.id,
    )
    return account


@tracer.wrap()
def create_account(
    session: Session, account_name: str, params: AccountParams
) -> db.Account:
    """
    Create an account with the supplied params but without creating default project or agent.
    """
    account_repository = db.AccountRepository(session)

    # Check if the account exists
    found_account = get_account(session, account_name)
    if found_account:
        raise ValueError(f"Account {account_name} already exists.")

    # Only create an account if the account name does not exist
    account = account_repository.create_account(account_name, **asdict(params))
    return account


@tracer.wrap()
def update_account(
    session: Session, account_name: str, params: AccountParams
) -> db.Account:
    """
    Update an account with the supplied params.
    """
    account_repository = db.AccountRepository(session)

    # Check if the account exists
    updated_account = account_repository.update_account(account_name, **asdict(params))
    if updated_account is None:
        raise ValueError(f"Account {account_name} does not exist.")
    return updated_account


@tracer.wrap()
def delete_account(session: Session, account_name: str):
    account_repository = db.AccountRepository(session)
    account_repository.delete_account(account_name)
