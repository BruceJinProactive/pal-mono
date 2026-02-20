import copy
import uuid
from dataclasses import asdict
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from db.repositories.account_repository import AccountRepositoryAsync
from db.tables.accounts import AccountStatus
from db.tables.change_log import ChangeResourceType
from db.tables.types import SubscriptionStatus
from services.account_service.schema import AccountParams
from services.auth_types import UserContext
from services.history_service import change_log_context
from utils.log import logger


async def get_account_async(
    async_session: AsyncSession, account_name: str
) -> Optional[db.Account]:
    """Get an account by name asynchronously."""
    account_repository = AccountRepositoryAsync(async_session)
    account = await account_repository.get_account(account_name=account_name)
    return account


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
    load_subscription: bool = False,
) -> List[db.Account]:
    """
    Filter accounts by a flexible name match using a keyword.

    Args:
        session: Database session
        keyword: Optional keyword to filter by name/display_name
        load_subscription: If True, eagerly loads current subscription to avoid N+1 queries
    """
    account_repository = db.AccountRepository(session)
    accounts = account_repository.filter_accounts_by_name(keyword, load_subscription)
    return accounts


def filter_accounts(
    session: Session,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    status: Optional[List[AccountStatus]] = None,
    subscription_status: Optional[List[SubscriptionStatus]] = None,
    load_subscription: bool = False,
) -> Tuple[List[db.Account], int]:
    """
    Filter accounts with pagination and multiple filter options.

    Args:
        session: Database session
        keyword: Optional keyword to filter by name/display_name
        page: Page number (1-indexed)
        page_size: Number of items per page
        status: Optional list of account statuses to filter by
        subscription_status: Optional list of subscription statuses to filter by
        load_subscription: If True, eagerly loads current subscription to avoid N+1 queries

    Returns:
        Tuple of (list of accounts, total count)
    """
    account_repository = db.AccountRepository(session)
    return account_repository.filter_accounts(
        keyword=keyword,
        page=page,
        page_size=page_size,
        status=status,
        subscription_status=subscription_status,
        load_subscription=load_subscription,
    )


def create_account(
    session: Session,
    context: UserContext,
    account_name: str,
    params: AccountParams,
    lead_id: uuid.UUID | None,
    auto_commit: bool,
) -> db.Account:
    """
    Create an account with the supplied params but without creating default project or agent.
    """
    account_repository = db.AccountRepository(session, auto_commit=False)
    lead_repository = db.LeadRepository(session, auto_commit=auto_commit)

    # Check if the account exists
    found_account = get_account(session, account_name)
    if found_account:
        raise ValueError(f"Account {account_name} already exists.")

    # Check if lead exists
    if lead_id:
        lead = lead_repository.get_lead_by_id(lead_id)
        if not lead:
            raise ValueError(f"Lead id {lead_id} not found.")
        if lead.account_id:
            logger.warning(
                f"Lead is already linked to the account: {lead.account_id}, it will be unlinked."
            )

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Account,
        author=context.email,
        auto_commit=auto_commit,
    ) as ctx:
        account = account_repository.create_account(account_name, **asdict(params))
        # Update the context with the actual account ID and record
        ctx.account_id = account.id
        ctx.resource_id = str(account.id)
        ctx.new_record = account

    if lead_id:
        lead_repository.update_lead(lead_id=lead_id, account_id=account.id)

    return account


def update_account(
    session: Session,
    account_name: str,
    params: AccountParams,
    context: UserContext,
    expected_version: int | None = None,
) -> db.Account:
    """
    Update an account with the supplied params.
    """
    account_repository = db.AccountRepository(session, auto_commit=False)

    # Get the current account state
    existing_account = account_repository.get_account(account_name)
    if existing_account is None:
        raise ValueError(f"Account {account_name} does not exist.")

    # Keep a copy of the account before the update because sqlalchemy uses in place update
    old_account = copy.copy(existing_account)

    with change_log_context(
        session=session,
        account_id=existing_account.id,
        resource_id=str(existing_account.id),
        resource_type=ChangeResourceType.Account,
        author=context.email,
        old_record=old_account,
    ) as ctx:
        # Update the account
        updated_account = account_repository.update_account(
            account_name, expected_version, **asdict(params)
        )
        if updated_account is None:
            raise ValueError(f"Failed to update account {account_name}")
        ctx.new_record = updated_account

    return updated_account


def delete_account(
    session: Session, account_name: str, hard_delete: bool, context: UserContext
):
    account_repository = db.AccountRepository(session, auto_commit=False)

    # Get the account before deleting
    account = account_repository.get_account(account_name)
    if account is None:
        logger.warning(f"Account {account_name} does not exist, cannot delete.")
        return

    with change_log_context(
        session=session,
        account_id=account.id,
        resource_id=str(account.id),
        resource_type=ChangeResourceType.Account,
        author=context.email,
        old_record=account,
    ):
        # Delete the account
        account_repository.delete_account(account_name, hard_delete)
