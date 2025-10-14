from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import CheckPoint
from utils.log import logger


class CheckpointRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_checkpoint(self, checkpoint: CheckPoint) -> CheckPoint:
        # Validate required fields
        if not checkpoint.project_id:
            raise ValueError("project_id is required and cannot be empty")
        if not checkpoint.name or not checkpoint.name.strip():
            raise ValueError("name is required and cannot be empty")

        # Explicitly copy allowed fields to avoid SQLAlchemy internals
        db_checkpoint = CheckPoint(
            project_id=checkpoint.project_id,
            name=checkpoint.name,
            description=checkpoint.description,
            image_url=checkpoint.image_url,
            is_active=(
                checkpoint.is_active if checkpoint.is_active is not None else False
            ),
            group=checkpoint.group,
            rules=checkpoint.rules,
        )

        try:
            self.session.add(db_checkpoint)
            self.session.commit()
            self.session.refresh(db_checkpoint)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating checkpoint: {e}")
            raise

        return db_checkpoint
