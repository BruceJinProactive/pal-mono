import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from api.schemas.chat.message import Message

from . import _implementation
from .schema import ProjectParams


def create_project(
    session: Session,
    context: UserContext,
    account_name: str,
    project_name: str,
    params: ProjectParams,
    auto_commit: bool = True,
) -> db.Project:
    """
    Create a new project for a specific account using provided parameters.

    Args:
        session (Session): The database connection.
        context (UserContext): Information for the current user
        account_name (str): The name of the account to which the project belongs.
        project_name (str): The unique name of the project to be created
        params (ProjectParams): The detailed configs of the project to be created.
        auto_commit (bool): New project will be committed automatically if True.

    Returns:
        Project: The newly created project.
    """
    return _implementation.create_project(
        session, context, account_name, project_name, params, auto_commit
    )


def update_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    params: ProjectParams,
) -> db.Project:
    """
    Update the specified project with the provided params.

    Args:
        session (Session): The database connection.
        context (UserContext): Information for the current user
        project_id (uuid.UUID): The uuid of the project to update.
        params (ProjectParams): The detailed configs of the project to be updated.

    Returns:
        Project: The updated project.
    """
    return _implementation.update_project(session, context, project_id, params)


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


def get_project_by_name(session: Session, project_name: str) -> db.Project | None:
    """
    Gets a specific project by name.

    Args:
        session (Session): The database connection.
        project_name (str): The name of the project.

    Returns:
        The Project that matches the given unique name, or None if no such Project exists.
    """

    return _implementation.get_project_by_name(session, project_name)


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


def delete_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
) -> None:
    """
    Deletes a specific project using its unique identifier.

    Args:
        session (Session): The database connection.
        context (UserContext): Information for the current user
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        None
    """
    return _implementation.delete_project(session, context, project_id)


async def get_project_async(session: AsyncSession, message: Message) -> db.Project:
    """
    Asynchronously gets a specific project using the channel platform and identifier from the message.

    Args:
        session (AsyncSession): The asynchronous database connection.
        message (Message): The message containing the channel and recipient information.

    Returns:
        The Project with the matching channel platform and identifier, or raises a ValueError if no such Project exists.
    """
    return await _implementation.get_project_async(session, message)


def get_project_sync(session: Session, message: Message) -> db.Project:
    """
    Synchronously gets a specific project using the channel platform and identifier from the message.

    Args:
        session (Session): The database connection.
        message (Message): The message containing the channel and recipient information.

    Returns:
        The Project with the matching channel platform and identifier, or raises a ValueError if no such Project exists.
    """
    return _implementation.get_project_sync(session, message)


__all__ = [
    "create_project",
    "update_project",
    "get_project",
    "get_project_by_name",
    "replace_project_channel_identifiers",
    "update_project_config",
    "replace_project_config",
    "delete_project",
    "get_project_async",
    "get_project_sync",
    "ProjectParams",
]
