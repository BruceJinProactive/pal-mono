from typing import List, Optional

from sqlalchemy.orm import Session

import db

from . import _implementation


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


__all__ = [
    "get_accounts",
    "get_account",
    "create_account_with_defaults",
]
