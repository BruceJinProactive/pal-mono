from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.user import UserData
from db.tables.users import User
from utils.log import logger


def _to_data(row: User) -> UserData:
    """Convert an ORM User to a UserData."""
    return UserData(
        id=row.id,
        account_id=row.account_id,
        raw_config=dict(row.raw_config) if row.raw_config else {},
        channel_identifiers=(
            tuple(row.channel_identifiers)
            if row.channel_identifiers is not None
            else None
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class UserRepository:
    """Async-only repository for User records.

    All methods return ``UserData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, user_id: uuid.UUID) -> UserData | None:
        """Retrieve a single user by its primary key."""
        try:
            result = await self.session.execute(select(User).filter(User.id == user_id))
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving user by ID")
            raise

    async def list_by_account_id(self, account_id: uuid.UUID) -> list[UserData]:
        """List all users for a given account."""
        try:
            result = await self.session.execute(
                select(User)
                .filter(User.account_id == account_id)
                .order_by(User.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing users by account ID")
            raise

    async def get_by_channel_identifier(
        self, channel_identifier: str
    ) -> UserData | None:
        """Retrieve a user by a channel identifier (e.g. phone number)."""
        try:
            result = await self.session.execute(
                select(User).filter(
                    User.channel_identifiers.contains([channel_identifier])
                )
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving user by channel identifier")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: UserData) -> None:
        """Create a new user.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = User(
                id=record.id,
                account_id=record.account_id,
                raw_config=dict(record.raw_config),
                channel_identifiers=(
                    list(record.channel_identifiers)
                    if record.channel_identifiers is not None
                    else []
                ),
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating user: {e}")
            raise

    async def delete(self, user_id: uuid.UUID) -> UserData | None:
        """Delete a user by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(select(User).filter(User.id == user_id))
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting user: {e}")
            raise
