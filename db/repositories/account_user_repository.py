import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import AccountUser
from db.tables.types import AccountUserStatus
from utils.log import logger


class AccountUserRepository:
    """Repository for managing user memberships in accounts.

    IMPORTANT: This tracks membership only (membership ≠ permissions).
    Roles are assigned via ResourceRoleAssignmentRepository.
    This separation allows flexible role assignment on different resources.
    """

    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_by_user_and_account(
        self, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> Optional[AccountUser]:
        """Retrieve account user by user and account IDs.

        Args:
            user_id: UUID of the user
            account_id: UUID of the account

        Returns:
            AccountUser object or None if not found
        """
        try:
            return (
                self.session.query(AccountUser)
                .filter(
                    AccountUser.user_id == user_id,
                    AccountUser.account_id == account_id,
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account user: {e}")
            return None

    def get_by_user_id(self, user_id: uuid.UUID) -> Optional[AccountUser]:
        """Get any AccountUser record for a user (first match).

        Used for looking up user display information (name, email) when
        we don't care which account membership we use.

        Args:
            user_id: UUID of the user

        Returns:
            AccountUser object or None if not found
        """
        try:
            return (
                self.session.query(AccountUser)
                .filter(AccountUser.user_id == user_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account user by user_id: {e}")
            return None

    def get_by_email_and_account(
        self, email: str, account_id: uuid.UUID
    ) -> Optional[AccountUser]:
        """Get active account user by email and account ID (case-insensitive).

        Only returns active members. Deactivated members are not returned,
        allowing them to be re-invited.

        Args:
            email: Email address to look up
            account_id: UUID of the account

        Returns:
            AccountUser object or None if not found or not active
        """
        try:
            normalized_email = email.strip().lower()
            return (
                self.session.query(AccountUser)
                .filter(
                    AccountUser.email.is_not(None),
                    func.lower(AccountUser.email) == normalized_email,
                    AccountUser.account_id == account_id,
                    AccountUser.status == AccountUserStatus.active,
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account user by email: {e}")
            return None

    def is_member(self, user_id: uuid.UUID, account_id: uuid.UUID) -> bool:
        """Check if user is an active member of account.

        Args:
            user_id: UUID of the user
            account_id: UUID of the account

        Returns:
            True if user is an active member, False otherwise
        """
        try:
            count = (
                self.session.query(AccountUser)
                .filter(
                    AccountUser.user_id == user_id,
                    AccountUser.account_id == account_id,
                    AccountUser.status == AccountUserStatus.active,
                )
                .count()
            )
            return count > 0
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error checking membership: {e}")
            return False

    def get_users_for_account(
        self, account_id: uuid.UUID, status: Optional[AccountUserStatus] = None
    ) -> list[AccountUser]:
        """Get all users for an account.

        Args:
            account_id: UUID of the account
            status: Optional status filter (e.g., active, deactivated)

        Returns:
            List of AccountUser objects, ordered by added_at desc
        """
        try:
            query = self.session.query(AccountUser).filter(
                AccountUser.account_id == account_id
            )

            if status:
                query = query.filter(AccountUser.status == status)

            return query.order_by(AccountUser.added_at.desc()).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving users for account: {e}")
            return []

    def get_accounts_for_user(
        self, user_id: uuid.UUID, status: Optional[AccountUserStatus] = None
    ) -> list[AccountUser]:
        """Get all accounts for a user.

        Args:
            user_id: UUID of the user
            status: Optional status filter (e.g., active, deactivated)

        Returns:
            List of AccountUser objects, ordered by added_at desc
        """
        try:
            query = self.session.query(AccountUser).filter(
                AccountUser.user_id == user_id
            )

            if status:
                query = query.filter(AccountUser.status == status)

            return query.order_by(AccountUser.added_at.desc()).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving accounts for user: {e}")
            return []

    def create(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        email: str,
        name: str,
        added_by: Optional[uuid.UUID] = None,
        status: AccountUserStatus = AccountUserStatus.active,
    ) -> AccountUser:
        """Create new account membership.

        If membership already exists, returns the existing one.

        Args:
            account_id: UUID of the account
            user_id: UUID of the user
            email: Email address for the user (required)
            name: Display name for the user (required)
            added_by: Optional UUID of user who added this member (None for self-onboarding)
            status: Membership status (default: active)

        Returns:
            The created or existing AccountUser object

        Raises:
            SQLAlchemyError: If there's a database error during creation
        """
        try:
            # Check if membership already exists
            existing = self.get_by_user_and_account(user_id, account_id)
            if existing:
                logger.info(
                    f"Account membership already exists: user {user_id} in account {account_id}"
                )
                return existing

            # Create new membership
            db_account_user = AccountUser(
                id=uuid.uuid4(),
                account_id=account_id,
                user_id=user_id,
                added_by=added_by,
                status=status,
                email=email,
                name=name,
            )
            self.session.add(db_account_user)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_account_user)
            logger.info(
                f"Created account membership: user {user_id} in account {account_id}"
            )
            return db_account_user
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating account membership: {e}")
            raise

    def update_status(
        self, user_id: uuid.UUID, account_id: uuid.UUID, new_status: AccountUserStatus
    ) -> Optional[AccountUser]:
        """Update user's membership status in account.

        Args:
            user_id: UUID of the user
            account_id: UUID of the account
            new_status: New status to set

        Returns:
            Updated AccountUser object or None if not found

        Raises:
            SQLAlchemyError: If there's a database error during update
        """
        try:
            db_account_user = self.get_by_user_and_account(user_id, account_id)
            if not db_account_user:
                logger.warning(
                    f"Account membership not found: user {user_id} in account {account_id}"
                )
                return None

            db_account_user.status = new_status

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_account_user)
            logger.info(
                f"Updated membership status to {new_status.value}: user {user_id} in account {account_id}"
            )
            return db_account_user
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating membership status: {e}")
            raise

    def update_user_info(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        email: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[AccountUser]:
        """Update user's email and name in account membership.

        Args:
            user_id: UUID of the user
            account_id: UUID of the account
            email: Optional email to update (if None, keeps existing)
            name: Optional name to update (if None, keeps existing)

        Returns:
            Updated AccountUser object or None if not found

        Raises:
            SQLAlchemyError: If there's a database error during update
        """
        try:
            db_account_user = self.get_by_user_and_account(user_id, account_id)
            if not db_account_user:
                logger.warning(
                    f"Account membership not found: user {user_id} in account {account_id}"
                )
                return None

            # Update fields if provided
            if email is not None:
                db_account_user.email = email
            if name is not None:
                db_account_user.name = name

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_account_user)
            logger.info(
                f"Updated user info: user {user_id} in account {account_id} "
                f"(email={email}, name={name})"
            )
            return db_account_user
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating user info: {e}")
            raise

    def delete(self, user_id: uuid.UUID, account_id: uuid.UUID) -> bool:
        """Hard delete account membership.

        Args:
            user_id: UUID of the user
            account_id: UUID of the account

        Returns:
            True if deleted, False if not found
        """
        try:
            db_account_user = self.get_by_user_and_account(user_id, account_id)
            if not db_account_user:
                logger.warning(
                    f"Account membership not found: user {user_id} in account {account_id}"
                )
                return False

            self.session.delete(db_account_user)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            logger.info(
                f"Deleted account membership: user {user_id} in account {account_id}"
            )
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting account membership: {e}")
            return False
