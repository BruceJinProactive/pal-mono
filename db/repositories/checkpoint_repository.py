from uuid import UUID

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

    def list_checkpoints(self, project_id: UUID) -> list[CheckPoint]:
        """Get all checkpoints for a project."""
        try:
            checkpoints = (
                self.session.query(CheckPoint)
                .filter(CheckPoint.project_id == project_id)
                .all()
            )
            return checkpoints
        except SQLAlchemyError as e:
            logger.error(f"Error listing checkpoints: {e}")
            raise

    def get_checkpoint(self, checkpoint_id: UUID) -> CheckPoint | None:
        """Get a checkpoint by ID."""
        try:
            checkpoint = (
                self.session.query(CheckPoint)
                .filter(CheckPoint.id == checkpoint_id)
                .first()
            )
            return checkpoint
        except SQLAlchemyError as e:
            logger.error(f"Error getting checkpoint: {e}")
            raise

    def delete_checkpoint(self, checkpoint_id: UUID) -> bool:
        """Delete a checkpoint by ID. Returns True if deleted, False if not found."""
        try:
            checkpoint = self.get_checkpoint(checkpoint_id)
            if not checkpoint:
                return False

            self.session.delete(checkpoint)
            self.session.commit()
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting checkpoint: {e}")
            raise
