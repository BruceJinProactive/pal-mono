import uuid
from datetime import datetime

from ddtrace import tracer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from db.tables import User
from utils.log import logger


class UserRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    @tracer.wrap()
    async def get_user_by_channel_identifier(
        self, account_id: uuid.UUID, channel_identifier: str
    ) -> User | None:
        """
        Retrieve a user by the channel identifier asynchronously.
        Args:
            account_id (uuid.UUID): The account ID associated with the user.
            channel_identifier (str): The identifier of the channel (e.g., phone number).
        Returns:
            User or None if no such user is found.
        """
        if not account_id:
            raise ValueError("'account_id' must be provided")
        if not channel_identifier:
            raise ValueError("'channel_identifier' must be provided")

        # Use the `contains` operator to search for the channel identifier
        query = select(User).filter(
            User.account_id == account_id,
            User.channel_identifiers.contains([channel_identifier]),
        )
        result = await self.session.execute(query)
        # In a rare case that multiple users are found with the same channel identifier, we return the first one.
        # A long term fix on the DB race condition prevention should be made to avoid this.
        user = result.scalars().first()
        return user

    @tracer.wrap()
    async def create_user(
        self, account_id: uuid.UUID, channel_identifier: str = ""
    ) -> User:
        """
        Create a new user asynchronously.
        Args:
            account_id (uuid.UUID): The account ID associated with the user.
            channel_identifier (str): The identifier of the channel (e.g., phone number).
        Returns:
            User: The newly created user.
        """
        db_user = User(account_id=account_id, channel_identifiers=[channel_identifier])
        self.session.add(db_user)
        await self.session.flush()
        await self.session.refresh(db_user)

        return db_user


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    @tracer.wrap()
    def get_users(self, skip: int = 0, limit: int = 100):
        return self.session.query(User).offset(skip).limit(limit).all()

    @tracer.wrap()
    def get_users_by_account_id(
        self, account_id: uuid.UUID, min_create_time: datetime | None = None
    ):
        # no argument validation needed
        try:
            return (
                self.session.query(User)
                .filter(
                    User.account_id == account_id,
                    User.created_at >= (min_create_time or datetime.min),
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving users: {e}")
            return []

    @tracer.wrap()
    def get_user_by_channel_identifier(
        self, account_id: uuid.UUID, channel_identifier: str
    ):
        """
        Retrieve a user by the channel identifier.

        Args:
            account_id (uuid.UUID): The account ID associated with the user.
            channel_identifier (str): The identifier of the channel (e.g., phone number).

        Returns:
            User or None if no such user is found.
        """
        if not account_id:
            raise ValueError("'account_id' must be provided")
        if not channel_identifier:
            raise ValueError("'channel_identifier' must be provided")

        # Use the `contains` operator to search for the channel identifier
        user = (
            self.session.query(User)
            .filter(
                User.account_id == account_id,
                User.channel_identifiers.contains([channel_identifier]),
            )
            .first()
        )
        return user

    @tracer.wrap()
    def get_user_by_id(self, user_id: uuid.UUID):
        query = self.session.query(User).filter(
            User.id == user_id,
        )
        user = query.first()
        return user

    @tracer.wrap()
    def create_user(self, account_id: uuid.UUID, channel_identifier: str = ""):
        db_user = User(account_id=account_id, channel_identifiers=[channel_identifier])
        self.session.add(db_user)
        self.session.commit()
        return db_user

    @tracer.wrap()
    def update_user(self, user_id: uuid.UUID, raw_config: dict):
        query = self.session.query(User).filter(User.id == user_id)
        user = query.first()
        if user:
            user.raw_config.update(raw_config)
            self.session.commit()
            return user
        return None
