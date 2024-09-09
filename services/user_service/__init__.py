import uuid
from typing import List

from sqlalchemy.orm import Session

import db.tables as db

from . import _implementation


def get_user_by_channel(
    db: Session,
    account_id: uuid.UUID,
    channel_platform: str,
    channel_identifier: str,
    create_new_user: bool = False,
) -> db.User | None:
    """
    Retrieve a user based on the provided account ID, channel platform, and channel identifier.

    Args:
        db (Session): The database session to use for the query.
        account_id (uuid.UUID): The unique identifier of the account.
        channel_platform (str): The platform of the channel (e.g., 'SMS', 'WhatsApp').
        channel_identifier (str): The identifier of the channel.
        create_new_user (bool, optional): Flag indicating whether to create a new user if one does not exist. Defaults to False.

    Returns:
        db.User | None: The retrieved user if found, otherwise None.
    """
    return _implementation.get_user_by_channel(
        db, account_id, channel_platform, channel_identifier, create_new_user
    )


def get_users_by_account_id(
    db: Session,
    account_id: uuid.UUID,
) -> List[db.User]:
    """
    Retrieve a list of users associated with the provided account ID.

    Args:
        db (Session): The database session to use for the query.
        account_id (uuid.UUID): The unique identifier of the account.

    Returns:
        List[db.User]: A list of users associated with the account.
    """
    return _implementation.get_users_by_account_id(db, account_id)


__all__ = ["get_user_by_channel", "get_users_by_account_id"]
