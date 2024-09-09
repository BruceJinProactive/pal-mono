import uuid

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import User
from utils.log import logger


class UserRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_users(self, skip: int = 0, limit: int = 100):
        return self.db.query(User).offset(skip).limit(limit).all()

    def get_users_by_account_id(self, account_id: uuid.UUID):
        # no argument validation needed

        try:
            return self.db.query(User).filter(User.account_id == account_id).all()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error retrieving users: {e}")
            return []

    def get_user_by_channel(
        self, account_id: uuid.UUID, channel_platform: str, channel_identifier: str
    ):
        if not account_id:
            raise ValueError("'account_id' must be provided")
        if not channel_platform:
            raise ValueError("'channel_platform' must be provided")
        if not channel_identifier:
            raise ValueError("'channel_identifier' must be provided")

        query = (
            self.db.query(User)
            .filter(
                User.account_id == account_id,
                text("(raw_config->>'channel_platform') = :channel_platform"),
                text("(raw_config->>'channel_identifier') = :channel_identifier"),
            )
            .params(
                channel_platform=channel_platform, channel_identifier=channel_identifier
            )
        )
        user = query.first()
        return user

    def get_user_by_id(self, user_id: uuid.UUID):
        query = self.db.query(User).filter(
            User.id == user_id,
        )
        user = query.first()
        return user

    def create_user(self, account_id: uuid.UUID):
        db_user = User(account_id=account_id)
        self.db.add(db_user)
        self.db.commit()
        return db_user

    def update_user(self, user_id: uuid.UUID, raw_config: dict):
        query = self.db.query(User).filter(User.id == user_id)
        user = query.first()
        if user:
            user.raw_config.update(raw_config)
            self.db.commit()
            return user
        return None
