from typing import List, Optional

from sqlalchemy.orm import Session

import db

from . import _implementation
from .schema import AccountParams


def get_accounts(session: Session) -> List[db.Account]:
    """
    Retrieve a list of all Accounts.

    Args:
        session (Session): The database session.

    Returns:
        List[Account]: A list of all Accounts.
    """
    return _implementation.get_accounts(session)


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


def create_account_with_defaults(session: Session, account_name: str) -> db.Account:
    """
    Creates a new account with default settings.

    Args:
        session (Session): The database session.
        account_name (str): The name of the new account.

    Returns:
        Account: The created account
    """
    return _implementation.create_account_with_defaults(session, account_name)


def create_account(
    session: Session, account_name: str, params: AccountParams
) -> db.Account:
    """
    Create an account in the database based on the provided account name and
    parameters. Account will not be created if the account_name already exists.

    Args:
        session (Session): The database session used to interact with the database.
        account_name (str): The name of the account to be created.
        params (AccountParams): The parameters containing details for the account
        to be created.

    Returns:
        Account: The newly created account object from the database.
    Raises:
        ValueError: If the account name already exists in the database.
    """
    return _implementation.create_account(session, account_name, params)


def update_account(
    session: Session, account_name: str, params: AccountParams
) -> db.Account:
    """
    Updates the account details with the provided parameters.

    Args:
        session (Session): The database session used to interact with the database.
        account_name (str): The name of the account to be updated.
        params (AccountParams): The parameters containing details for the account
        to be updated.

    Returns:
        Account: The updated account object from the database.
    Raises:
        ValueError: If the account name does not exist in the database.
    """
    return _implementation.update_account(session, account_name, params)


def delete_account(session: Session, account_name: str):
    """
    Delete the account identified by name.
    """
    return _implementation.delete_account(session, account_name)


def filter_accounts_by_name(
    session: Session,
    keyword: Optional[str] = None,
    limit: int = 20,
) -> List[db.Account]:
    """
    Filter accounts by a flexible name match using a keyword.
    Returns a limited number of results (default 20) to prevent returning too much data.

    Args:
        session (Session): The database session.
        keyword (Optional[str], optional): The keyword to search for in account names.
        limit (int, optional): Maximum number of results to return. Defaults to 20.

    Returns:
        List[db.Account]: Accounts matching the keyword filter.
    """
    return _implementation.filter_accounts_by_name(session, keyword, limit)


__all__ = [
    "AccountParams",
    "get_accounts",
    "get_account",
    "mget_accounts",
    "filter_accounts_by_name",
    "create_account_with_defaults",
    "create_account",
    "update_account",
    "delete_account",
]
