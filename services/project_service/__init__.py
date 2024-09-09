import uuid
from typing import Any, Dict

from sqlalchemy.orm import Session

from . import _implementation


def get_project(db: Session, project_id: uuid.UUID):
    """
    Gets a specific project using its unique identifier.

    Args:
        db (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        The Project with the matching unique identifier, or None if no such Project exists.
    """

    return _implementation.get_project(db, project_id)


def update_project_config(
    db: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Updates specific key-value pairs in the configuration of a given project.

    Args:
        db (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project whose configuration is being updated.
        config (Dict[str, Any]): A dictionary containing the config keys to update in the project's configuration.

    Returns:
        None
    """

    return _implementation.update_project_config(db, project_id, config)


def replace_project_config(
    db: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Replaces entire configuration of a given project.

    Args:
        db (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project whose configuration is being replaced.
        config (Dict[str, Any]): A dictionary containing the config that will replace the existing project's configuration.

    Returns:
        None
    """

    return _implementation.replace_project_config(db, project_id, config)


__all__ = ["get_project", "update_project_config", "replace_project_config"]
