from typing import Optional

from requests import Session

from db.tables import Account

from . import _implementation


def get_account(db: Session, account_name: str) -> Optional[Account]:
    """
    Retrieve an Account by its name.

    Args:
        db (Session): The database session.
        account_name (str): The name of the Account to retrieve.

    Returns:
        Account: The Account with the given name, or None if no such Account is found.
    """
    return _implementation.get_account(db, account_name)


def create_account_with_defaults(db: Session, account_name: str):
    """
    Creates a new account with default settings.

    Args:
        db (Session): The database session.
        account_name (str): The name of the new account.

    Returns:
        None
    """
    return _implementation.create_account_with_defaults(db, account_name)


__all__ = [
    "get_account",
    "create_account_with_defaults",
]
