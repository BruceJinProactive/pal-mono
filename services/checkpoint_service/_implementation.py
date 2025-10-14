from sqlalchemy.orm import Session

import db


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    checkpoint_repository = db.CheckpointRepository(session)
    return checkpoint_repository.create_checkpoint(checkpoint)
