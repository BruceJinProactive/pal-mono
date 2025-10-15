from uuid import UUID

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


def list_checkpoints(session: Session, project_id: UUID) -> list[db.CheckPoint]:
    """
    List all checkpoints for a project.

    Args:
        session (Session): The database session to use for the query.
        project_id (UUID): The UUID of the project.

    Returns:
        list[db.CheckPoint]: List of checkpoints for the project.
    """
    return _implementation.list_checkpoints(session, project_id)


def get_checkpoint(session: Session, checkpoint_id: UUID) -> db.CheckPoint | None:
    """
    Get a checkpoint by ID.

    Args:
        session (Session): The database session to use for the query.
        checkpoint_id (UUID): The UUID of the checkpoint.

    Returns:
        db.CheckPoint | None: The checkpoint if found, None otherwise.
    """
    return _implementation.get_checkpoint(session, checkpoint_id)


def update_checkpoint(
    session: Session, checkpoint_id: UUID, updates: dict
) -> db.CheckPoint | None:
    """
    Update a checkpoint by ID.

    Args:
        session (Session): The database session to use for the transaction.
        checkpoint_id (UUID): The UUID of the checkpoint to update.
        updates (dict): Dictionary of fields to update.

    Returns:
        db.CheckPoint | None: The updated checkpoint if found, None otherwise.
    """
    return _implementation.update_checkpoint(session, checkpoint_id, updates)


def delete_checkpoint(session: Session, checkpoint_id: UUID) -> bool:
    """
    Delete a checkpoint by ID.

    Args:
        session (Session): The database session to use for the transaction.
        checkpoint_id (UUID): The UUID of the checkpoint to delete.

    Returns:
        bool: True if the checkpoint was deleted, False if not found.
    """
    return _implementation.delete_checkpoint(session, checkpoint_id)


__all__ = [
    "create_checkpoint",
    "list_checkpoints",
    "get_checkpoint",
    "update_checkpoint",
    "delete_checkpoint",
]
