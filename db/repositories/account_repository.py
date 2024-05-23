from sqlalchemy.orm import Session

from db.tables import Account, Project


class AccountRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_accounts(self, skip: int = 0, limit: int = 100):
        return self.db.query(Account).offset(skip).limit(limit).all()

    def get_account(self, account_id: int = None, account_name: str = None):
        account_id_exists = account_id is not None and account_id > 0
        account_name_exists = account_name is not None and account_name.strip() != ""

        if not account_id_exists and not account_name_exists:
            raise ValueError("Either 'account_id' or 'account_name' must be provided")

        query = self.db.query(Account)
        if account_id_exists:
            query = query.filter(Account.id == account_id)
        if account_name_exists:
            query = query.filter(Account.name == account_name)

        return query.first()

    def update_account(self, account_id: int, account_name: str = None):
        db_account = self.db.query(Account).filter(Account.id == account_id).first()
        if db_account:
            if account_name is not None:
                db_account.name = account_name
            self.db.commit()
            self.db.refresh(db_account)
        return db_account

    def delete_account(self, account_id: int):
        db_account = self.db.query(Account).filter(Account.id == account_id).first()
        if db_account:
            self.db.delete(db_account)
            self.db.commit()
        return db_account

    def create_account(self, account_name: str):
        db_account = Account(account_name=account_name)
        self.db.add(db_account)
        self.db.commit()
        self.db.refresh(db_account)
        return db_account

    def create_account_with_project(self, account_name: str):
        # Create a new account
        db_account = Account(name=account_name)
        self.db.add(db_account)
        self.db.commit()  # Commit to generate ID for db_account

        # Create a new project associated with the new account
        db_project = Project(account_id=db_account.id)
        self.db.add(db_project)
        self.db.commit()

        # Associate the project with the account (optional if bidirectional relationship is needed)
        db_account.projects.append(db_project)
        self.db.commit()

        return db_account
