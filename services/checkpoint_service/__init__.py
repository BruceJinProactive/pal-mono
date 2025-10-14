from sqlalchemy.orm import Session

import db

from . import _implementation


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    """
    Create a new checkpoint in the database.

    Args:
        session (Session): The database session to use for the transaction.
        checkpoint (db.CheckPoint): The checkpoint object to create.

    Returns:
        db.CheckPoint: The created checkpoint with database-generated fields.
    """
    return _implementation.create_checkpoint(session, checkpoint)


__all__ = ["create_checkpoint"]
