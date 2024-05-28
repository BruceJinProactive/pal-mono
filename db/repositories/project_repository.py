from sqlalchemy.orm import Session

from db.tables import Project


class ProjectRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_project(self, account_id: int):
        db_project = Project(account_id=account_id)
        self.db.add(db_project)
        self.db.commit()
        return db_project
