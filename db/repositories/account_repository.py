import uuid
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Account
from utils.log import logger


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_accounts(self, skip: int = 0, limit: int = 100) -> List[Account]:
        """Retrieve a list of accounts with pagination."""
        try:
            return self.session.query(Account).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving accounts: {e}")
            return []

    def get_account(self, account_name: str) -> Optional[Account]:
        """Retrieve a single account by its name."""
        try:
            return (
                self.session.query(Account).filter(Account.name == account_name).first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account: {e}")
            return None

    def delete_account(self, account_name: str) -> Optional[Account]:
        """Delete an account by its name."""
        try:
            db_account = (
                self.session.query(Account).filter(Account.name == account_name).first()
            )
            if db_account:
                self.session.delete(db_account)
                self.session.commit()
            return db_account
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting account: {e}")
            return None

    def create_account(self, account_name: str) -> Account:
        """Create a new account with a unique UUID."""
        try:
            existing_account = self.get_account(account_name)
            if existing_account:
                return existing_account
            db_account = Account(id=uuid.uuid4(), name=account_name)
            self.session.add(db_account)
            self.session.commit()
            self.session.refresh(db_account)
            return db_account
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating account: {e}")
            raise
