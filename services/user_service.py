from sqlalchemy.orm import Session

import db.tables as db
from db.repositories.user_repository import UserRepository


def get_user(
    db: Session,
    account_id: str,
    channel_platform: str,
    channel_identifier: str,
    create_new_user: bool = False,
) -> db.User | None:
    user_repository = UserRepository(db)
    user = user_repository.get_user(
        account_id=account_id,
        channel_platform=channel_platform,
        channel_identifier=channel_identifier,
    )

    if user:
        return user

    if create_new_user:
        new_user = user_repository.create_user(account_id=account_id)
        user_repository.update_user(
            user_id=str(new_user.id),
            raw_config={
                "channel_platform": channel_platform,
                "channel_identifier": channel_identifier,
            },
        )
        return new_user

    return None
