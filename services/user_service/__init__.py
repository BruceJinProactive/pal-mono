import uuid
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.chat.message import Message

from . import _implementation


def get_user_by_channel_identifier(
    session: Session,
    account_id: uuid.UUID,
    channel_identifier: str,
    create_new_user: bool = False,
) -> db.User | None:
    """
    Retrieve a user based on the provided account ID, channel platform, and channel identifier.

    Args:
        session (Session): The database session to use for the query.
        account_id (uuid.UUID): The unique identifier of the account.
        channel_identifier (str): The identifier of the channel, such as "whatsapp:+1xxxxxxxxxx"
        create_new_user (bool, optional): Flag indicating whether to create a new user if one does not exist. Defaults to False.

    Returns:
        db.User | None: The retrieved user if found, otherwise None.
    """
    return _implementation.get_user_by_channel_identifier(
        session, account_id, channel_identifier, create_new_user
    )


def get_users_by_account_id(
    session: Session,
    account_id: uuid.UUID,
) -> List[db.User]:
    """
    Retrieve a list of users associated with the provided account ID.

    Args:
        session (Session): The database session to use for the query.
        account_id (uuid.UUID): The unique identifier of the account.

    Returns:
        List[db.User]: A list of users associated with the account.
    """
    return _implementation.get_users_by_account_id(session, account_id)


async def get_user_async(
    session: AsyncSession, project: db.Project, message: Message
) -> Tuple[Optional[db.User], bool]:
    """
    Asynchronously retrieve a user based on the provided project and message.

    Args:
        session (AsyncSession): The asynchronous database session to use for the query.
        project (db.Project): The project associated with the user.
        message (Message): The message containing the channel and sender information.

    Returns:
        Tuple[Optional[db.User], bool]: A tuple containing the retrieved user if found (otherwise None) and a boolean indicating if an opt-in message is needed.
    """
    return await _implementation.get_user_async(session, project, message)


__all__ = [
    "get_user_by_channel_identifier",
    "get_users_by_account_id",
    "get_user_async",
]
