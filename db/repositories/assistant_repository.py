from sqlalchemy.orm import Session

from db.tables import Assistant


class AssistantRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_assistant(self, project_id: int):
        db_assistant = Assistant(project_id=project_id)
        self.db.add(db_assistant)
        self.db.commit()
        return db_assistant
