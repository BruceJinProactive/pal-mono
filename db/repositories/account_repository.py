import uuid
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Account
from db.tables.accounts import AccountStatus
from utils.log import logger


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

    def filter_accounts_by_name(self, keyword: Optional[str] = None) -> List[Account]:
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

            return query.all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error filtering accounts by name: {e}")
            return []

    def update_account(self, account_name: str, **kwargs) -> Account | None:
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
                    self.session.delete(db_account)
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
