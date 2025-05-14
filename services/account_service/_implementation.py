import copy
import uuid
from dataclasses import asdict
from typing import List, Optional

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from db.tables.change_log import ChangeResourceType
from services import history_service
from services.account_service.schema import AccountParams
from utils.log import logger


def get_accounts(session: Session) -> List[db.Account]:
    account_repository = db.AccountRepository(session)
    accounts = account_repository.get_accounts()
    return accounts


def get_account(session: Session, account_name: str) -> Optional[db.Account]:
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name=account_name)
    return account


def get_account_by_id(session: Session, account_id: uuid.UUID) -> Optional[db.Account]:
    """Get an account by its ID."""
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account_by_id(account_id=account_id)
    return account


def mget_accounts(session: Session, account_names: List[str]) -> List[db.Account]:
    account_repository = db.AccountRepository(session)
    accounts = account_repository.get_accounts_by_names(account_names)
    return accounts


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


def create_account(
    session: Session,
    account_name: str,
    params: AccountParams,
    auto_commit: bool,
    context: UserContext,
) -> db.Account:
    """
    Create an account with the supplied params but without creating default project or agent.
    """
    account_repository = db.AccountRepository(session, auto_commit=False)

    # Check if the account exists
    found_account = get_account(session, account_name)
    if found_account:
        raise ValueError(f"Account {account_name} already exists.")

    try:
        # Only create an account if the account name does not exist
        account = account_repository.create_account(account_name, **asdict(params))
        history_service.create_change_log(
            session=session,
            account_id=account.id,
            resource_type=ChangeResourceType.Account,
            resource_id=str(account.id),
            author=context.email,
            old_record=None,
            new_record=account,
        )
        if auto_commit:
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create account due to error: {e}")
        raise

    return account


def update_account(
    session: Session, account_name: str, params: AccountParams, context: UserContext
) -> db.Account:
    """
    Update an account with the supplied params.
    """
    account_repository = db.AccountRepository(session, auto_commit=False)

    # Get the current account state
    existing_account = account_repository.get_account(account_name)
    if existing_account is None:
        raise ValueError(f"Account {account_name} does not exist.")

    try:
        # Keep a copy of the account before the update because sqlalchemy uses in place update
        old_account = copy.copy(existing_account)
        # Update the account
        updated_account = account_repository.update_account(
            account_name, **asdict(params)
        )
        history_service.create_change_log(
            session=session,
            account_id=existing_account.id,
            resource_type=ChangeResourceType.Account,
            resource_id=str(existing_account.id),
            author=context.email,
            old_record=old_account,
            new_record=updated_account,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update account due to error: {e}")
        raise

    return updated_account


def delete_account(session: Session, account_name: str, context: UserContext):
    account_repository = db.AccountRepository(session, auto_commit=False)

    # Get the account before deleting
    account = account_repository.get_account(account_name)
    if account is None:
        logger.warn(f"Account {account_name} does not exist, cannot delete.")
        return

    try:
        # Delete the account
        account_repository.delete_account(account_name)
        history_service.create_change_log(
            session=session,
            account_id=account.id,
            resource_type=ChangeResourceType.Account,
            resource_id=str(account.id),
            author=context.email,
            old_record=account,
            new_record=None,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete account due to error: {e}")
        raise
