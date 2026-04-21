from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.account_user import AccountUserData
from db.tables.account_user import AccountUser
from db.tables.types import AccountUserStatus
from utils.log import logger


def _to_data(row: AccountUser) -> AccountUserData:
    """Convert an ORM AccountUser to an AccountUserData."""
    return AccountUserData(
        id=row.id,
        account_id=row.account_id,
        user_id=row.user_id,
        status=row.status.value if row.status else "",
        added_at=row.added_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        name=row.name,
        email=row.email,
        added_by=row.added_by,
    )


class AccountUserRepository:
    """Async-only repository for AccountUser records.

    All methods return ``AccountUserData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_and_account(
        self, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> AccountUserData | None:
        """Retrieve account user by user and account IDs."""
        try:
            result = await self.session.execute(
                select(AccountUser).filter(
                    AccountUser.user_id == user_id,
                    AccountUser.account_id == account_id,
                )
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving account user")
            raise

    async def get_by_email_and_account(
        self, email: str, account_id: uuid.UUID
    ) -> AccountUserData | None:
        """Get active account user by email and account ID (case-insensitive)."""
        try:
            normalized_email = email.strip().lower()
            result = await self.session.execute(
                select(AccountUser).filter(
                    AccountUser.email.is_not(None),
                    func.lower(func.trim(AccountUser.email)) == normalized_email,
                    AccountUser.account_id == account_id,
                    AccountUser.status == AccountUserStatus.active,
                )
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving account user by email")
            raise

    async def get_users_for_account(
        self, account_id: uuid.UUID, status: str | None = None
    ) -> list[AccountUserData]:
        """Get all users for an account, optionally filtered by status."""
        try:
            query = select(AccountUser).filter(AccountUser.account_id == account_id)
            if status:
                query = query.filter(AccountUser.status == AccountUserStatus(status))
            query = query.order_by(AccountUser.added_at.desc())
            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving users for account")
            raise

    async def get_accounts_for_user(
        self, user_id: uuid.UUID, status: str | None = None
    ) -> list[AccountUserData]:
        """Get all accounts for a user, optionally filtered by status."""
        try:
            query = select(AccountUser).filter(AccountUser.user_id == user_id)
            if status:
                query = query.filter(AccountUser.status == AccountUserStatus(status))
            query = query.order_by(AccountUser.added_at.desc())
            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving accounts for user")
            raise

    async def is_member(self, user_id: uuid.UUID, account_id: uuid.UUID) -> bool:
        """Check if user is an active member of account."""
        try:
            result = await self.session.execute(
                select(func.count())
                .select_from(AccountUser)
                .filter(
                    AccountUser.user_id == user_id,
                    AccountUser.account_id == account_id,
                    AccountUser.status == AccountUserStatus.active,
                )
            )
            return (result.scalar() or 0) > 0
        except Exception:
            logger.exception("Error checking membership")
            raise

    async def create(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str,
        name: str,
        added_by: uuid.UUID | None = None,
    ) -> AccountUserData:
        """Create new account membership.

        Idempotent: returns existing membership if one already exists for
        the given (account_id, user_id) pair.
        """
        try:
            existing = await self.get_by_user_and_account(user_id, account_id)
            if existing:
                return existing

            normalized_email = email.strip().lower()
            row = AccountUser(
                id=uuid.uuid4(),
                account_id=account_id,
                user_id=user_id,
                added_by=added_by,
                status=AccountUserStatus.active,
                email=normalized_email,
                name=name,
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating account membership: {e}")
            raise

    async def update_status(
        self, user_id: uuid.UUID, account_id: uuid.UUID, new_status: str
    ) -> AccountUserData | None:
        """Update user membership status."""
        try:
            result = await self.session.execute(
                select(AccountUser).filter(
                    AccountUser.user_id == user_id,
                    AccountUser.account_id == account_id,
                )
            )
            row = result.scalars().first()
            if not row:
                return None
            row.status = AccountUserStatus(new_status)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating membership status: {e}")
            raise

    async def delete(self, user_id: uuid.UUID, account_id: uuid.UUID) -> bool:
        """Hard delete account membership. Returns True if deleted."""
        try:
            result = await self.session.execute(
                select(AccountUser).filter(
                    AccountUser.user_id == user_id,
                    AccountUser.account_id == account_id,
                )
            )
            row = result.scalars().first()
            if not row:
                return False
            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting account membership: {e}")
            raise
