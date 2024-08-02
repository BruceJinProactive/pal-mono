from sqlalchemy import text
from sqlalchemy.orm import Session

from db.tables import User


class UserRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_users(self, skip: int = 0, limit: int = 100):
        return self.db.query(User).offset(skip).limit(limit).all()

    def get_user(self, project_id: str, channel_platform: str, channel_identifier: str):
        if not project_id:
            raise ValueError("'project_id' must be provided")
        if not channel_platform:
            raise ValueError("'channel_platform' must be provided")
        if not channel_identifier:
            raise ValueError("'channel_identifier' must be provided")

        query = (
            self.db.query(User)
            .filter(
                User.project_id == int(project_id),
                text("(raw_config->>'channel_platform') = :channel_platform"),
                text("(raw_config->>'channel_identifier') = :channel_identifier"),
            )
            .params(
                channel_platform=channel_platform, channel_identifier=channel_identifier
            )
        )
        user = query.first()
        return user

    def create_user(self, project_id: str):
        db_user = User(project_id=int(project_id))
        self.db.add(db_user)
        self.db.commit()
        return db_user

    def update_user(
        self,
        user_id: str,
        raw_config: dict,
    ):
        if not user_id:
            raise ValueError("'user_id' must be provided")
        query = self.db.query(User).filter(User.id == int(user_id))

        user = query.first()
        if user:
            # Update the user.raw_config dictionary with the values from raw_config
            user.raw_config.update(raw_config)

            self.db.commit()
        return user
