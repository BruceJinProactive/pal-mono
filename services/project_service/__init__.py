import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.chat.message import Message
from services.auth_types import UserContext

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
    expected_version: int | None = None,
    auto_commit: bool = True,
) -> db.Project:
    """
    Update the specified project with the provided params.

    Args:
        session (Session): The database connection.
        context (UserContext): Information for the current user
        project_id (uuid.UUID): The uuid of the project to update.
        params (ProjectParams): The detailed configs of the project to be updated.
        auto_commit (bool): Changes will be committed automatically if True.

    Returns:
        Project: The updated project.
    """
    return _implementation.update_project(
        session, context, project_id, params, auto_commit, expected_version
    )


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


def get_projects_by_account_id(
    session: Session, account_id: uuid.UUID
) -> List[db.Project]:
    """
    Gets all projects belonging to a specific account.

    Args:
        session (Session): The database connection.
        account_id (uuid.UUID): The unique identifier of the account.

    Returns:
        List[Project]: A list of projects belonging to the account.
    """
    return _implementation.get_projects_by_account_id(session, account_id)


def get_projects_by_ids(
    session: Session, project_ids: List[uuid.UUID]
) -> List[db.Project]:
    """
    Gets multiple projects by their IDs.

    Args:
        session (Session): The database connection.
        project_ids (List[uuid.UUID]): List of project IDs to fetch.

    Returns:
        List[Project]: A list of projects matching the provided IDs.
    """
    return _implementation.get_projects_by_ids(session, project_ids)


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


async def get_project_by_id_async(
    session: AsyncSession, project_id: uuid.UUID
) -> db.Project | None:
    """
    Asynchronously gets a specific project using its unique identifier.

    Args:
        session (AsyncSession): The asynchronous database connection.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        The Project with the matching unique identifier, or None if no such Project exists.
    """
    return await _implementation.get_project_by_id_async(session, project_id)


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


def get_projects_by_phone_number(
    session: Session, phone_number: str
) -> List[db.Project]:
    """
    Find all projects associated with a phone number by checking different channel prefixes.

    Args:
        session (Session): The database connection.
        phone_number (str): The phone number to search for (e.g., "+15551234567").

    Returns:
        List of Projects associated with the phone number. Empty list if none found.
    """
    return _implementation.get_projects_by_phone_number(session, phone_number)


def batch_create_projects(
    session: Session,
    context: UserContext,
    account_name: str,
    agent_id: uuid.UUID,
    location_data: List[ProjectParams],
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Create multiple projects for a given account.

    Args:
        session (Session): The database connection.
        context (UserContext): Information for the current user.
        account_name (str): The name of the account to create projects under.
        agent_id (uuid.UUID): The agent ID to use for all projects.
        location_data (List[ProjectParams]): List of project parameters for each location.
        auto_commit (bool): Whether to commit changes automatically.

    Returns:
        Dict containing creation results.
    """
    return _implementation.batch_create_projects(
        session,
        context,
        account_name,
        agent_id,
        location_data,
        auto_commit,
    )


def batch_update_projects(
    session: Session,
    context: UserContext,
    account_name: str,
    project_updates: List[Dict[str, Any]],
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """Update multiple projects for a given account.

    Args:
        session (Session): Database session.
        context (UserContext): User context for authentication.
        account_name (str): Name of the account that owns the projects.
        project_updates (List[Dict[str, Any]]): List of project updates.
        auto_commit (bool): Whether to commit changes automatically.

    Returns:
        Dict containing update results.
    """
    return _implementation.batch_update_projects(
        session,
        context,
        account_name,
        project_updates,
        auto_commit,
    )


def batch_delete_projects(
    session: Session,
    context: UserContext,
    account_name: str,
    project_ids: List[uuid.UUID],
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """Delete multiple projects for a given account.

    Args:
        session (Session): Database session.
        context (UserContext): User context for authentication.
        account_name (str): Name of the account that owns the projects.
        project_ids (List[uuid.UUID]): List of project UUIDs to delete.
        auto_commit (bool): Whether to commit changes automatically.

    Returns:
        Dict containing deletion results.
    """
    return _implementation.batch_delete_projects(
        session,
        context,
        account_name,
        project_ids,
        auto_commit,
    )


async def create_project_async(
    async_session: AsyncSession,
    context: UserContext,
    account_name: str,
    project_name: str,
    params: ProjectParams,
) -> db.Project:
    """Create a project asynchronously.

    Args:
        async_session (AsyncSession): The asynchronous database connection.
        context (UserContext): Information for the current user.
        account_name (str): The name of the account to which the project belongs.
        project_name (str): The unique name of the project to be created.
        params (ProjectParams): The detailed configs of the project to be created.

    Returns:
        Project: The newly created project.
    """
    return await _implementation.create_project_async(
        async_session, context, account_name, project_name, params
    )


async def delete_project_async(
    async_session: AsyncSession,
    context: UserContext,
    project_id: uuid.UUID,
) -> None:
    """Delete a project and its voice_configs asynchronously.

    Args:
        async_session (AsyncSession): The asynchronous database connection.
        context (UserContext): Information for the current user.
        project_id (uuid.UUID): The unique identifier of the project.

    Returns:
        None
    """
    return await _implementation.delete_project_async(
        async_session, context, project_id
    )


__all__ = [
    "create_project",
    "update_project",
    "get_project",
    "get_project_by_name",
    "get_projects_by_account_id",
    "replace_project_channel_identifiers",
    "update_project_config",
    "replace_project_config",
    "delete_project",
    "get_project_by_id_async",
    "get_project_async",
    "get_project_sync",
    "get_projects_by_phone_number",
    "batch_create_projects",
    "batch_update_projects",
    "batch_delete_projects",
    "create_project_async",
    "delete_project_async",
    "ProjectParams",
]
