from sqlalchemy.orm import Session

from db.tables import Assistant


class AssistantRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_assistants(self, skip: int = 0, limit: int = 100):
        return self.db.query(Assistant).offset(skip).limit(limit).all()

    def get_assistant(self, assistant_id: int):
        if assistant_id is None or assistant_id <= 0:
            raise ValueError("'assistant_id' must be provided and greater than 0")

        query = self.db.query(Assistant)
        query = query.filter(Assistant.id == assistant_id)

        return query.first()

    def create_assistant(self, project_id: int):
        db_assistant = Assistant(project_id=project_id)
        self.db.add(db_assistant)
        self.db.commit()
        return db_assistant
