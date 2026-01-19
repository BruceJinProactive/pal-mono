import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from db.tables import (
    Account,
    AccountSubscription,
    AccountUser,
    Agent,
    Conversation,
    Message,
    Project,
    User,
)
from db.tables.accounts import AccountStatus
from utils.log import logger


class AccountRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_account(self, account_name: str) -> Account | None:
        """Retrieve an account by name asynchronously."""
        try:
            query = (
                select(Account)
                .filter(Account.name == account_name)
                .filter(Account.status != AccountStatus.deleted)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving account: {e}")
            return None

    async def get_account_by_id(self, account_id: uuid.UUID) -> Account | None:
        """Retrieve an account by its ID asynchronously."""
        try:
            query = (
                select(Account)
                .filter(Account.id == account_id)
                .filter(Account.status != AccountStatus.deleted)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving account by ID: {e}")
            return None

    async def get_account_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Account | None:
        """Retrieve an account by Stripe customer ID asynchronously."""
        try:
            query = (
                select(Account)
                .filter(Account.stripe_customer_id == stripe_customer_id)
                .filter(Account.status != AccountStatus.deleted)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving account by Stripe customer ID: {e}")
            return None


class AccountRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_account(self, account_name: str) -> Account | None:
        accounts = self.get_accounts_by_names([account_name])
        if accounts:
            return accounts[0]
        else:
            return None

    def get_account_by_id(self, account_id: uuid.UUID) -> Account | None:
        """Retrieve an account by its ID."""

        try:
            return (
                self.session.query(Account)
                .filter(Account.id == account_id)
                .filter(Account.status != AccountStatus.deleted)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account by ID: {e}")
            return None

    def get_accounts_by_names(self, account_names: List[str]) -> List[Account]:
        """Retrieve multiple accounts by their names."""
        try:
            return (
                self.session.query(Account)
                .filter(Account.name.in_(account_names))
                .filter(Account.status != AccountStatus.deleted)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account: {e}")
            return []

    def filter_accounts_by_name(
        self, keyword: Optional[str] = None, load_subscription: bool = False
    ) -> List[Account]:
        """
        Filter accounts by a flexible name or display_name match, using a case-insensitive partial match.
        If no keyword is provided, returns all accounts.
        """
        try:
            query = self.session.query(Account).filter(
                Account.status != AccountStatus.deleted
            )

            if keyword:
                query = query.filter(
                    (Account.name.ilike(f"%{keyword}%"))
                    | (Account.display_name.ilike(f"%{keyword}%"))
                )

            if load_subscription:
                query = query.outerjoin(
                    AccountSubscription,
                    Account.current_subscription_id == AccountSubscription.id,
                ).options(
                    joinedload(Account.subscriptions).joinedload(
                        AccountSubscription.subscription_plan
                    )
                )

            return query.all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error filtering accounts by name: {e}")
            return []

    def update_account(
        self, account_name: str, expected_version: int | None = None, **kwargs
    ) -> Account | None:
        """Update account details based on the account ID and provided fields."""
        try:
            db_account = (
                self.session.query(Account)
                .filter(Account.name == account_name)
                .filter(Account.status != AccountStatus.deleted)
                .first()
            )
            if not db_account:
                return None

            if expected_version and db_account.updated_at:
                if expected_version != int(db_account.updated_at.timestamp()):
                    raise ValueError(
                        "Version mismatch: Account has been modified by another process."
                    )

            for key, value in kwargs.items():
                if value is not None and hasattr(db_account, key):
                    setattr(db_account, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_account)
            return db_account
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating account: {e}")
            raise

    def delete_account(self, account_name: str, hard_delete: bool) -> Optional[Account]:
        """Delete an account by its name."""
        try:
            db_account = (
                self.session.query(Account).filter(Account.name == account_name).first()
            )
            if db_account:
                if hard_delete:
                    logger.warn(
                        f"Hard deleting account {account_name} from the database!"
                    )
                    # Delete dependent records in correct order to avoid FK violations
                    account_id = db_account.id

                    # 1. Get user IDs for this account (needed for messages/conversations)
                    user_ids = [
                        u.id
                        for u in self.session.query(User.id)
                        .filter(User.account_id == account_id)
                        .all()
                    ]

                    if user_ids:
                        # 2. Delete messages for conversations belonging to these users
                        conversation_ids = [
                            c.id
                            for c in self.session.query(Conversation.id)
                            .filter(Conversation.user_id.in_(user_ids))
                            .all()
                        ]
                        if conversation_ids:
                            self.session.query(Message).filter(
                                Message.conversation_id.in_(conversation_ids)
                            ).delete(synchronize_session=False)

                        # 3. Delete conversations for these users
                        self.session.query(Conversation).filter(
                            Conversation.user_id.in_(user_ids)
                        ).delete(synchronize_session=False)

                    # 4. Delete users (callers) for this account
                    self.session.query(User).filter(
                        User.account_id == account_id
                    ).delete(synchronize_session=False)

                    # 5. Delete account user memberships
                    self.session.query(AccountUser).filter(
                        AccountUser.account_id == account_id
                    ).delete(synchronize_session=False)

                    # 6. Delete projects for this account
                    self.session.query(Project).filter(
                        Project.account_id == account_id
                    ).delete(synchronize_session=False)

                    # 7. Delete agents for this account
                    self.session.query(Agent).filter(
                        Agent.account_id == account_id
                    ).delete(synchronize_session=False)

                    # 8. Delete account subscriptions
                    self.session.query(AccountSubscription).filter(
                        AccountSubscription.account_id == account_id
                    ).delete(synchronize_session=False)

                    # 9. Delete the account
                    self.session.query(Account).filter(Account.id == account_id).delete(
                        synchronize_session=False
                    )
                else:
                    db_account.status = AccountStatus.deleted

                if self.auto_commit:
                    self.session.commit()
                else:
                    self.session.flush()
            return db_account
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting account: {e}")
            raise

    def create_account(self, account_name: str, **kwargs) -> Account:
        """Create a new account with a unique UUID."""
        try:
            existing_account = self.get_account(account_name)
            if existing_account:
                return existing_account
            db_account = Account(id=uuid.uuid4(), name=account_name)
            for key, value in kwargs.items():
                if value is not None and hasattr(db_account, key):
                    setattr(db_account, key, value)
            self.session.add(db_account)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_account)
            return db_account
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating account: {e}")
            raise

    def get_accounts_with_coupons(self) -> List[Account]:
        """Retrieve all accounts that have a Stripe coupon assigned."""
        try:
            return (
                self.session.query(Account)
                .filter(Account.stripe_coupon_id.isnot(None))
                .filter(Account.status != AccountStatus.deleted)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving accounts with coupons: {e}")
            return []
