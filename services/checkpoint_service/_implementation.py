from uuid import UUID

from sqlalchemy.orm import Session

import db


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.create_checkpoint(checkpoint)


def list_checkpoints(session: Session, project_id: UUID) -> list[db.CheckPoint]:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.list_checkpoints(project_id)


def get_checkpoint(session: Session, checkpoint_id: UUID) -> db.CheckPoint | None:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.get_checkpoint(checkpoint_id)


def update_checkpoint(
    session: Session, checkpoint_id: UUID, updates: dict
) -> db.CheckPoint | None:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.update_checkpoint(checkpoint_id, updates)


def delete_checkpoint(session: Session, checkpoint_id: UUID) -> bool:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.delete_checkpoint(checkpoint_id)
