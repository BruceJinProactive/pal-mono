import uuid

from sqlalchemy.orm import Session

from db.tables import Project


class ProjectRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_project(
        self, project_name: str, account_id: uuid.UUID, assistant_id: uuid.UUID
    ) -> Project:
        db_project = Project(
            name=project_name, account_id=account_id, assistant_id=assistant_id
        )
        self.db.add(db_project)
        self.db.commit()
        return db_project

    def get_project(self, project_id: str) -> Project | None:
        return self.db.query(Project).filter(Project.id == int(project_id)).first()
