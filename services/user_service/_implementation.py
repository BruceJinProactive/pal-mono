import uuid
from typing import List

from sqlalchemy.orm import Session

import db.tables as db
from db.repositories.user_repository import UserRepository


def get_user_by_channel(
    db: Session,
    account_id: uuid.UUID,
    channel_platform: str,
    channel_identifier: str,
    create_new_user: bool = False,
) -> db.User | None:
    user_repository = UserRepository(db)
    user = user_repository.get_user_by_channel(
        account_id=account_id,
        channel_platform=channel_platform,
        channel_identifier=channel_identifier,
    )

    if user:
        return user

    if create_new_user:
        new_user = user_repository.create_user(account_id=account_id)
        user_repository.update_user(
            user_id=new_user.id,
            raw_config={
                "channel_platform": channel_platform,
                "channel_identifier": channel_identifier,
            },
        )
        return new_user

    return None


def get_user_by_channel_identifier(
    db: Session,
    account_id: uuid.UUID,
    channel_identifier: str,
    create_new_user: bool = False,
) -> db.User | None:
    user_repository = UserRepository(db)
    user = user_repository.get_user_by_channel_identifier(
        account_id=account_id,
        channel_identifier=channel_identifier,
    )

    if user:
        return user

    if create_new_user:
        new_user = user_repository.create_user(
            account_id=account_id, channel_identifier=channel_identifier
        )
        return new_user

    return None


def get_users_by_account_id(
    db: Session,
    account_id: uuid.UUID,
) -> List[db.User]:
    user_repository = UserRepository(db)
    users = user_repository.get_users_by_account_id(account_id=account_id)

    return users
