from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.user_invitation import UserInvitationData
from db.tables.types import InvitationStatus
from db.tables.user_invitation import UserInvitation
from utils.log import logger


def _to_data(row: UserInvitation) -> UserInvitationData:
    """Convert an ORM UserInvitation to a UserInvitationData."""
    if row.status is None:
        raise ValueError("UserInvitation.status is unexpectedly NULL")

    return UserInvitationData(
        id=row.id,
        account_id=row.account_id,
        email=row.email,
        account_role=row.account_role,
        project_ids=(tuple(row.project_ids) if row.project_ids is not None else None),
        invited_by=row.invited_by,
        invitation_token=row.invitation_token,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
        status=row.status.value,
        created_at=row.created_at,
    )


class UserInvitationRepository:
    """Async-only repository for UserInvitation records.

    All methods return ``UserInvitationData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, invitation_id: uuid.UUID) -> UserInvitationData | None:
        """Retrieve a single invitation by its primary key."""
        try:
            result = await self.session.execute(
                select(UserInvitation).filter(UserInvitation.id == invitation_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving user invitation by ID")
            raise

    async def get_by_token(self, invitation_token: str) -> UserInvitationData | None:
        """Retrieve an invitation by its unique token."""
        try:
            result = await self.session.execute(
                select(UserInvitation).filter(
                    UserInvitation.invitation_token == invitation_token
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving user invitation by token")
            raise

    async def list_by_account_id(
        self, account_id: uuid.UUID
    ) -> list[UserInvitationData]:
        """List all invitations for a given account."""
        try:
            result = await self.session.execute(
                select(UserInvitation)
                .filter(UserInvitation.account_id == account_id)
                .order_by(UserInvitation.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing user invitations by account ID")
            raise

    async def list_by_email(self, email: str) -> list[UserInvitationData]:
        """List all invitations for a given email address."""
        try:
            result = await self.session.execute(
                select(UserInvitation)
                .filter(UserInvitation.email == email)
                .order_by(UserInvitation.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing user invitations by email")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: UserInvitationData) -> None:
        """Create a new user invitation.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = UserInvitation(
                id=record.id,
                account_id=record.account_id,
                email=record.email,
                account_role=record.account_role,
                project_ids=(
                    list(record.project_ids) if record.project_ids is not None else None
                ),
                invited_by=record.invited_by,
                invitation_token=record.invitation_token,
                expires_at=record.expires_at,
                accepted_at=record.accepted_at,
                status=InvitationStatus(record.status),
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating user invitation: {e}")
            raise

    async def delete(self, invitation_id: uuid.UUID) -> UserInvitationData | None:
        """Delete a user invitation by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(UserInvitation).filter(UserInvitation.id == invitation_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting user invitation: {e}")
            raise
