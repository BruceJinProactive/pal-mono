import uuid
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from services.auth_types import UserContext

from . import _implementation
from .schema import AccountParams


async def get_account_async(
    async_session: AsyncSession, account_name: str
) -> Optional[db.Account]:
    """
    Retrieve an Account by its name asynchronously.

    Args:
        async_session (AsyncSession): The async database session.
        account_name (str): The name of the Account to retrieve.

    Returns:
        Account: The Account with the given name, or None if no such Account is found.
    """
    return await _implementation.get_account_async(async_session, account_name)


def get_account(session: Session, account_name: str) -> Optional[db.Account]:
    """
    Retrieve an Account by its name.

    Args:
        session (Session): The database session.
        account_name (str): The name of the Account to retrieve.

    Returns:
        Account: The Account with the given name, or None if no such Account is found.
    """
    return _implementation.get_account(session, account_name)


def get_account_by_id(session: Session, account_id: uuid.UUID) -> Optional[db.Account]:
    """
    Retrieve an Account by its id.

    Args:
        session (Session): The database session.
        account_id (uuid.UUID): The id of the Account to retrieve.

    Returns:
        Account: The Account with the given name, or None if no such Account is found.
    """
    return _implementation.get_account_by_id(session, account_id)


def mget_accounts(session: Session, account_names: List[str]) -> List[db.Account]:
    """
    Retrieve multiple Accounts by names.

    Args:
        session (Session): The database session.
        account_names (List[str]): The names of the Accounts to retrieve.

    Returns:
        List[db.Account]: The Accounts that match the given names, or empty list if none matches.
    """
    return _implementation.mget_accounts(session, account_names)


def create_account(
    session: Session,
    context: UserContext,
    account_name: str,
    params: AccountParams,
    lead_id: uuid.UUID | None,
    auto_commit: bool = True,
) -> db.Account:
    """
    Create an account in the database based on the provided account name and
    parameters. Account will not be created if the account_name already exists.

    Args:
        session (Session): The database session used to interact with the database.
        context (UserContext): Information about the current user
        account_name (str): The name of the account to be created.
        params (AccountParams): The parameters containing details for the account
        to be created.
        lead_id (uuid.UUID): The ID of the lead that led to the creation of this account.
        auto_commit (bool): New account will be committed automatically if True.

    Returns:
        Account: The newly created account object from the database.
    Raises:
        ValueError: If the account name already exists in the database.
    """
    return _implementation.create_account(
        session, context, account_name, params, lead_id, auto_commit
    )


def update_account(
    session: Session,
    context: UserContext,
    account_name: str,
    params: AccountParams,
    expected_version: int | None = None,
) -> db.Account:
    """
    Updates the account details with the provided parameters.

    Args:
        session (Session): The database session used to interact with the database.
        account_name (str): The name of the account to be updated.
        params (AccountParams): The parameters containing details for the account
        to be updated.
        context (UserContext): Information about the current user

    Returns:
        Account: The updated account object from the database.
    Raises:
        ValueError: If the account name does not exist in the database.
    """
    return _implementation.update_account(
        session, account_name, params, context, expected_version
    )


def delete_account(
    session: Session, account_name: str, hard_delete: bool, context: UserContext
):
    """
    Delete the account identified by name.
    """
    return _implementation.delete_account(session, account_name, hard_delete, context)


def filter_accounts_by_name(
    session: Session,
    keyword: Optional[str] = None,
) -> List[db.Account]:
    """
    Filter accounts by a flexible name match using a keyword.

    Args:
        session (Session): The database session.
        keyword (Optional[str], optional): The keyword to search for in account names.

    Returns:
        List[db.Account]: Accounts matching the keyword filter.
    """
    return _implementation.filter_accounts_by_name(session, keyword)


__all__ = [
    "AccountParams",
    "get_account",
    "get_account_async",
    "mget_accounts",
    "filter_accounts_by_name",
    "create_account",
    "update_account",
    "delete_account",
]
