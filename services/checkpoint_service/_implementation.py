from uuid import UUID

from sqlalchemy.orm import Session

import db


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.create_checkpoint(checkpoint)


def list_checkpoints(session: Session, project_id: UUID) -> list[db.CheckPoint]:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.list_checkpoints(project_id)
