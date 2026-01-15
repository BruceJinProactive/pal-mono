import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import UserInvitation
from db.tables.types import InvitationStatus
from utils.log import logger


class UserInvitationRepository:
    """Repository for managing team member invitations.

    On acceptance, creates:
    1. AccountUser record (membership)
    2. ResourceRoleAssignment record (role on account resource)
    """

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create(
        self,
        account_id: uuid.UUID,
        email: str,
        account_role: str,
        invited_by: uuid.UUID,
        invitation_token: str,
        expires_at: datetime,
    ) -> UserInvitation:
        """Create a new invitation.

        Args:
            account_id: UUID of the account
            email: Email address to invite
            account_role: Role to assign on acceptance (e.g., 'owner', 'manager', 'viewer')
            invited_by: UUID of user who sent the invitation
            invitation_token: Secure token (use secrets.token_urlsafe(48))
            expires_at: Expiration datetime

        Returns:
            The created UserInvitation object

        Raises:
            ValueError: If expires_at is not in the future
            SQLAlchemyError: If there's a database error during creation
        """
        try:
            # Validate expiration is in future
            now = datetime.now(timezone.utc)
            if expires_at <= now:
                raise ValueError("expires_at must be in the future")

            # Create new invitation
            db_invitation = UserInvitation(
                id=uuid.uuid4(),
                account_id=account_id,
                email=email,
                account_role=account_role,
                invited_by=invited_by,
                invitation_token=invitation_token,
                expires_at=expires_at,
                status=InvitationStatus.pending,
            )
            self.session.add(db_invitation)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_invitation)
            logger.info(
                f"Created invitation: {email} to account {account_id} with role {account_role}"
            )
            return db_invitation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating invitation: {e}")
            raise

    def get_by_token(self, token: str) -> Optional[UserInvitation]:
        """Retrieve invitation by token.

        Args:
            token: Unique invitation token

        Returns:
            UserInvitation object or None if not found
        """
        try:
            return (
                self.session.query(UserInvitation)
                .filter(UserInvitation.invitation_token == token)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving invitation by token: {e}")
            return None

    def get_by_id(self, invitation_id: uuid.UUID) -> Optional[UserInvitation]:
        """Retrieve invitation by ID.

        Args:
            invitation_id: UUID of the invitation

        Returns:
            UserInvitation object or None if not found
        """
        try:
            return (
                self.session.query(UserInvitation)
                .filter(UserInvitation.id == invitation_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving invitation by ID: {e}")
            return None

    def get_pending_for_account(self, account_id: uuid.UUID) -> list[UserInvitation]:
        """Get all pending invitations for an account.

        Args:
            account_id: UUID of the account

        Returns:
            List of pending UserInvitation objects, ordered by created_at desc
        """
        try:
            return (
                self.session.query(UserInvitation)
                .filter(
                    UserInvitation.account_id == account_id,
                    UserInvitation.status == InvitationStatus.pending,
                )
                .order_by(UserInvitation.created_at.desc())
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving pending invitations: {e}")
            return []

    def has_pending_for_email(self, account_id: uuid.UUID, email: str) -> bool:
        """Check if a pending invitation exists for an email in an account.

        Case-insensitive email comparison.

        Args:
            account_id: UUID of the account
            email: Email address to check

        Returns:
            True if a pending invitation exists, False otherwise
        """
        try:
            count = (
                self.session.query(UserInvitation)
                .filter(
                    UserInvitation.account_id == account_id,
                    func.lower(UserInvitation.email) == email.lower(),
                    UserInvitation.status == InvitationStatus.pending,
                )
                .count()
            )
            return count > 0
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error checking pending invitation: {e}")
            return False

    def get_for_email(self, email: str) -> list[UserInvitation]:
        """Get all invitations for an email address (across accounts).

        Args:
            email: Email address

        Returns:
            List of UserInvitation objects, ordered by created_at desc
        """
        try:
            return (
                self.session.query(UserInvitation)
                .filter(UserInvitation.email == email)
                .order_by(UserInvitation.created_at.desc())
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving invitations for email: {e}")
            return []

    def get_pending_for_email(self, email: str) -> list[UserInvitation]:
        """Get all pending (non-expired) invitations for an email address.

        Args:
            email: Email address

        Returns:
            List of pending UserInvitation objects, ordered by created_at desc
        """
        try:
            now = datetime.now(timezone.utc)
            return (
                self.session.query(UserInvitation)
                .filter(
                    UserInvitation.email == email,
                    UserInvitation.status == InvitationStatus.pending,
                    UserInvitation.expires_at > now,
                )
                .order_by(UserInvitation.created_at.desc())
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving pending invitations for email: {e}")
            return []

    def mark_as_accepted(self, invitation_id: uuid.UUID) -> Optional[UserInvitation]:
        """Mark invitation as accepted.

        Args:
            invitation_id: UUID of the invitation

        Returns:
            Updated UserInvitation object or None if not found

        Raises:
            SQLAlchemyError: If there's a database error during update
        """
        try:
            invitation = self.get_by_id(invitation_id)
            if not invitation:
                logger.warning(f"Invitation not found: {invitation_id}")
                return None

            invitation.status = InvitationStatus.accepted
            invitation.accepted_at = datetime.now(timezone.utc)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(invitation)
            logger.info(f"Marked invitation {invitation_id} as accepted")
            return invitation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error marking invitation as accepted: {e}")
            raise

    def mark_as_expired(self, invitation_id: uuid.UUID) -> Optional[UserInvitation]:
        """Mark invitation as expired.

        Args:
            invitation_id: UUID of the invitation

        Returns:
            Updated UserInvitation object or None if not found

        Raises:
            SQLAlchemyError: If there's a database error during update
        """
        try:
            invitation = self.get_by_id(invitation_id)
            if not invitation:
                logger.warning(f"Invitation not found: {invitation_id}")
                return None

            invitation.status = InvitationStatus.expired

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(invitation)
            logger.info(f"Marked invitation {invitation_id} as expired")
            return invitation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error marking invitation as expired: {e}")
            raise

    def update_expiration(
        self, invitation_id: uuid.UUID, new_expires_at: datetime
    ) -> Optional[UserInvitation]:
        """Update invitation expiration time.

        Args:
            invitation_id: UUID of the invitation
            new_expires_at: New expiration datetime

        Returns:
            Updated UserInvitation object or None if not found

        Raises:
            ValueError: If new_expires_at is not in the future
            SQLAlchemyError: If there's a database error during update
        """
        try:
            # Validate expiration is in future
            now = datetime.now(timezone.utc)
            if new_expires_at <= now:
                raise ValueError("new_expires_at must be in the future")

            invitation = self.get_by_id(invitation_id)
            if not invitation:
                logger.warning(f"Invitation not found: {invitation_id}")
                return None

            invitation.expires_at = new_expires_at

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(invitation)
            logger.info(
                f"Updated invitation {invitation_id} expiration to {new_expires_at}"
            )
            return invitation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating invitation expiration: {e}")
            raise

    def revoke(self, invitation_id: uuid.UUID) -> Optional[UserInvitation]:
        """Revoke an invitation.

        Args:
            invitation_id: UUID of the invitation

        Returns:
            Updated UserInvitation object or None if not found

        Raises:
            SQLAlchemyError: If there's a database error during update
        """
        try:
            invitation = self.get_by_id(invitation_id)
            if not invitation:
                logger.warning(f"Invitation not found: {invitation_id}")
                return None

            invitation.status = InvitationStatus.revoked

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(invitation)
            logger.info(f"Revoked invitation {invitation_id}")
            return invitation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error revoking invitation: {e}")
            raise

    def cleanup_expired(self) -> int:
        """Mark expired pending invitations as expired.

        Batch update: set status=expired where expires_at < now() and status=pending.
        Call this periodically (e.g., via cron job).

        Returns:
            Count of updated invitations
        """
        try:
            now = datetime.now(timezone.utc)
            count = (
                self.session.query(UserInvitation)
                .filter(
                    UserInvitation.status == InvitationStatus.pending,
                    UserInvitation.expires_at < now,
                )
                .update(
                    {UserInvitation.status: InvitationStatus.expired},
                    synchronize_session=False,
                )
            )

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(f"Marked {count} invitations as expired")
            return count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error cleaning up expired invitations: {e}")
            return 0
