import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from . import _implementation


def create_project(
    session: Session, project_name: str, account_id: uuid.UUID, agent_id: uuid.UUID
):
    """
    Creates a new project with the given name, account, and agent.

    Args:
        session (Session): The database connection.
        project_name (str): The name of the project.
        account_id (uuid.UUID): The unique identifier of the account to which the project belongs.
        agent_id (uuid.UUID): The unique identifier of the agent associated with the project.

    Returns:
        The newly created Project.
    """

    return _implementation.create_project(session, project_name, account_id, agent_id)


def get_project(session: Session, project_id: uuid.UUID):
    """
    Gets a specific project using its unique identifier.

    Args:
        session (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        The Project with the matching unique identifier, or None if no such Project exists.
    """

    return _implementation.get_project(session, project_id)


def replace_project_channel_identifiers(
    session: Session, project_id: uuid.UUID, channel_identifiers: List[str]
) -> None:
    """
    Replaces a project's channel identifiers.

    Args:
        session (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project whose configuration is being replaced.
        channel_identifiers (List[str]): A list of the new channel identifiers.

    Returns:
        None
    """

    return _implementation.replace_project_channel_identifiers(
        session, project_id, channel_identifiers
    )


def update_project_config(
    session: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Updates specific key-value pairs in the configuration of a given project.

    Args:
        session (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project whose configuration is being updated.
        config (Dict[str, Any]): A dictionary containing the config keys to update in the project's configuration.

    Returns:
        None
    """

    return _implementation.update_project_config(session, project_id, config)


def replace_project_config(
    session: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Replaces entire configuration of a given project.

    Args:
        session (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project whose configuration is being replaced.
        config (Dict[str, Any]): A dictionary containing the config that will replace the existing project's configuration.

    Returns:
        None
    """

    return _implementation.replace_project_config(session, project_id, config)


def delete_project(session: Session, project_id: uuid.UUID) -> None:
    """
    Deletes a specific project using its unique identifier.

    Args:
        session (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        None
    """
    return _implementation.delete_project(session, project_id)


__all__ = [
    "create_project",
    "get_project",
    "replace_project_channel_identifiers",
    "update_project_config",
    "replace_project_config",
    "delete_project",
]
