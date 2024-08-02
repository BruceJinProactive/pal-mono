from sqlalchemy.orm import Session

from db.repositories.user_repository import UserRepository


def get_user_id(
    db: Session,
    project_id: str,
    channel_platform: str,
    channel_identifier: str,
    create_new_user: bool = False,
) -> int | None:
    user_repository = UserRepository(db)
    user = user_repository.get_user(
        project_id=project_id,
        channel_platform=channel_platform,
        channel_identifier=channel_identifier,
    )

    if user:
        return user.id

    if create_new_user:
        new_user = user_repository.create_user(project_id=project_id)
        user_repository.update_user(
            user_id=str(new_user.id),
            raw_config={
                "channel_platform": channel_platform,
                "channel_identifier": channel_identifier,
            },
        )
        return new_user.id

    return None
