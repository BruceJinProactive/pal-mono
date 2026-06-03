import asyncio
import copy
import uuid
from dataclasses import asdict
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.chat.message import Message
from db.pal_repository.data_classes.voice_config import VoiceConfigData
from db.pal_repository.voice_config import VoiceConfigRepository
from db.repositories.project_repository import ProjectRepository, ProjectRepositoryAsync
from db.tables.change_log import ChangeResourceType
from services.auth_types import UserContext
from services.history_service import change_log_context
from services.number_service import NumberService
from utils.log import logger

from .. import account_service, agent_service, subscription_service
from .schema import ProjectParams

# Helper functions for change logging


def _release_number_safe(number: str) -> None:
    """Safely release a phone number with error handling."""
    try:
        number_service = NumberService()
        number_service.release_number_with_options(number, "return_to_pool")
    except Exception as e:
        logger.error(
            f"Failed to release phone number {number}: {str(e)}", exc_info=True
        )


def _create_project_data_snapshot(project):
    """Create a primitive data snapshot of project for cross-thread logging."""
    if project is None:
        return None

    return {
        "id": project.id,
        "name": project.name,
        "display_name": getattr(project, "display_name", None),
        "raw_config": getattr(project, "raw_config", getattr(project, "config", {})),
        "channel_identifiers": project.channel_identifiers,
        "store_hours": getattr(project, "store_hours", None),
        "address": getattr(project, "address", None),
        "product_info": getattr(project, "product_info", None),
        "service_instruction": getattr(project, "service_instruction", None),
        "order_integration_id": getattr(project, "order_integration_id", None),
        "timezone": getattr(project, "timezone", None),
        "transfer_message": getattr(project, "transfer_message", None),
        "reservation_link": getattr(project, "reservation_link", None),
        "ordering_link": getattr(project, "ordering_link", None),
        "call_forwarding_setup_completed": getattr(
            project, "call_forwarding_setup_completed", False
        ),
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "account_id": project.account_id,
        "agent_id": project.agent_id,
    }


def _create_mock_project_from_data(project_data):
    """Build a transient instance of the real Project model for diffing."""
    Project = db.Project  # mapped class from our model registry
    obj = Project()
    for key, value in (project_data or {}).items():
        setattr(obj, key, value)
    return obj


def _log_project_change_sync(
    sync_engine,
    author: str,
    account_id: uuid.UUID,
    project_id: uuid.UUID,
    operation_type: str,  # 'create' or 'delete'
    project_data=None,  # For delete operations, contains the project data before deletion
) -> None:
    """Helper function to run sync project change logging by re-querying ORM instances."""
    from sqlalchemy.orm import sessionmaker

    sync_session_factory = sessionmaker(bind=sync_engine)

    try:
        with sync_session_factory() as sync_session:
            if operation_type == "create":
                # For creation, create mock ORM object from captured project data
                new_project = _create_mock_project_from_data(project_data)
                old_project = None

                with change_log_context(
                    session=sync_session,
                    resource_type=ChangeResourceType.Project,
                    author=author,
                    account_id=account_id,
                    resource_id=str(project_id),
                    old_record=old_project,
                    new_record=new_project,
                    auto_commit=True,
                ):
                    pass

            elif operation_type == "delete":
                # For deletion, create mock ORM object from captured project data
                old_project = _create_mock_project_from_data(project_data)
                new_project = None

                with change_log_context(
                    session=sync_session,
                    resource_type=ChangeResourceType.Project,
                    author=author,
                    account_id=account_id,
                    resource_id=str(project_id),
                    old_record=old_project,
                    new_record=new_project,
                    auto_commit=True,
                ):
                    pass

            else:
                logger.warning(f"Unknown operation type: {operation_type}")

    except Exception as e:
        logger.error(f"Failed to log project {operation_type}: {e}", exc_info=True)


def create_project(
    session: Session,
    context: UserContext,
    account_name: str,
    project_name: str,
    params: ProjectParams,
    auto_commit: bool,
) -> db.Project:
    # validate parameters
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")
    if not params.agent_id:
        raise ValueError("Missing agent_id in request")

    agent = agent_service.get_agent(session, params.agent_id)
    if not agent or agent.account_id != account.id:
        raise ValueError("selected agent is not available in the account")

    # Add API channel with project name as identifier
    api_channel_identifier = f"api:{project_name}"
    if params.channel_identifiers is None:
        params.channel_identifiers = []
    if api_channel_identifier not in params.channel_identifiers:
        params.channel_identifiers.append(api_channel_identifier)

    project_repository = db.ProjectRepository(session, auto_commit=False)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=account.id,
        auto_commit=auto_commit,
    ) as ctx:
        project = project_repository.create_project(
            account.id, project_name, **asdict(params)
        )
        ctx.resource_id = str(project.id)
        ctx.new_record = project
    return project


def update_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    params: ProjectParams,
    auto_commit: bool,
    expected_version: int | None = None,
) -> db.Project:
    project_repository = db.ProjectRepository(session, auto_commit=False)

    existing_project = project_repository.get_project(project_id)
    if not existing_project:
        raise ValueError(f"Project {project_id} does not exist.")

    old_project = copy.copy(existing_project)
    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=existing_project.account.id,
        resource_id=str(project_id),
        old_record=old_project,
        auto_commit=auto_commit,
    ) as ctx:
        updated_project = project_repository.update_project(
            project_id, expected_version, **asdict(params)
        )
        if updated_project is None:
            raise ValueError(f"Failed to update project {project_id}")
        ctx.new_record = updated_project
        return updated_project


def get_project(session: Session, project_id: uuid.UUID) -> db.Project | None:
    project_repository = db.ProjectRepository(session)
    return project_repository.get_project(project_id)


def get_project_by_name(session: Session, project_name: str):
    project_repository = db.ProjectRepository(session)
    return project_repository.get_project_by_name(project_name)


def get_projects_by_account_id(session: Session, account_id: uuid.UUID):
    """
    Gets all projects belonging to a specific account.

    Args:
        session (Session): The database connection.
        account_id (uuid.UUID): The unique identifier of the account.

    Returns:
        List[Project]: A list of projects belonging to the account.
    """
    project_repository = db.ProjectRepository(session)
    return project_repository.get_projects_by_account_id(account_id)


def get_projects_by_ids(session: Session, project_ids: List[uuid.UUID]):
    """
    Gets multiple projects by their IDs.

    Args:
        session (Session): The database connection.
        project_ids (List[uuid.UUID]): List of project IDs to fetch.

    Returns:
        List[Project]: A list of projects matching the provided IDs.
    """
    project_repository = db.ProjectRepository(session)
    return project_repository.get_projects_by_ids(project_ids)


def update_project_config(
    session: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    project_repository = db.ProjectRepository(session)
    project_repository.update_project_config(project_id=project_id, config=config)


def replace_project_channel_identifiers(
    session: Session, project_id: uuid.UUID, channel_identifiers: List[str]
) -> None:
    project_repository = db.ProjectRepository(session)
    project_repository.replace_project_channel_identifiers(
        project_id=project_id, channel_identifiers=channel_identifiers
    )


def replace_project_config(
    session: Session, project_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    project_repository = db.ProjectRepository(session)
    project_repository.replace_project_config(project_id=project_id, config=config)


def delete_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
) -> None:
    project_repository = db.ProjectRepository(session, auto_commit=False)
    number_service = NumberService()

    existing_project = project_repository.get_project(project_id)
    if not existing_project:
        return

    unique_numbers = set()
    for identifier in existing_project.channel_identifiers or []:
        if identifier.startswith(("sms:", "voice:", "phone:")):
            number = identifier.split(":", 1)[1]
            unique_numbers.add(number)

    if unique_numbers:
        for number in unique_numbers:
            logger.info(
                "Returning phone number to pool from project.",
                extra={
                    "project_id": project_id,
                    "phone_number": number,
                },
            )
            try:
                number_service.release_number_with_options(number, "return_to_pool")
            except Exception as e:
                raise ValueError(f"Failed to release phone number {number}: {str(e)}")

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=existing_project.account.id,
        resource_id=str(existing_project.id),
        old_record=existing_project,
    ):
        project_repository.delete_project(project_id)


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
    project_repo = db.ProjectRepositoryAsync(session)
    return await project_repo.get_project(project_id)


async def get_project_async(session: AsyncSession, message: Message) -> db.Project:
    project_channel_identifier = (
        f"{message.channel.value}:{message.recipient_identifier}"
    )
    project_repo = db.ProjectRepositoryAsync(session)
    project = await project_repo.get_project_by_channel_identifier(
        project_channel_identifier
    )
    if project is None:
        raise ValueError(
            f"Project with channel platform '{message.channel.value}', "
            f"channel_identifier '{message.recipient_identifier}' not found."
        )
    return project


def get_project_sync(session: Session, message: Message) -> db.Project:
    project_channel_identifier = (
        f"{message.channel.value}:{message.recipient_identifier}"
    )
    project = db.ProjectRepository(session).get_project_by_channel_identifier(
        project_channel_identifier
    )
    if project is None:
        raise ValueError(
            f"Project with channel platform '{message.channel.value}', "
            f"channel_identifier '{message.recipient_identifier}' not found."
        )
    return project


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
    repository = ProjectRepository(session)
    return repository.get_projects_by_phone_number(phone_number)


def batch_create_projects(
    session: Session,
    context: UserContext,
    account_name: str,
    agent_id: uuid.UUID,
    location_data: List["ProjectParams"],
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Create multiple projects for a given account.

    Args:
        session: Database session
        context: User context for authentication
        account_name: Name of the account to create projects under
        agent_id: Agent ID to use for all projects
        location_data: List of project parameters for each location
        auto_commit: Whether to commit changes automatically

    Returns:
        Dict containing creation results
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    agent = agent_service.get_agent(session, agent_id)
    if not agent or agent.account_id != account.id:
        raise ValueError("Selected agent is not available in the account")

    results = []
    created_projects = []

    try:
        for i, project_params in enumerate(location_data):
            project_name = project_params.name or f"project_{i}"

            try:
                if getattr(project_params, "agent_id", None) is None:
                    project_params.agent_id = agent_id

                # Create the project
                project = create_project(
                    session=session,
                    context=context,
                    account_name=account_name,
                    project_name=project_name,
                    params=project_params,
                    auto_commit=False,
                )

                results.append(
                    {
                        "project_name": project.name,
                        "project_id": str(project.id),
                        "display_name": project.display_name,
                        "success": True,
                        "error_message": None,
                    }
                )

                created_projects.append(project)

                logger.info(f"Successfully created project: {project.name}")

            except Exception as e:
                logger.error(f"Failed to create project {project_name}: {e}")
                results.append(
                    {
                        "project_name": project_name,
                        "project_id": None,
                        "display_name": project_params.display_name,
                        "success": False,
                        "error_message": str(e),
                    }
                )

        if auto_commit:
            session.commit()
            logger.info(f"Successfully created {len(created_projects)} projects")
        else:
            session.flush()

    except Exception as e:
        session.rollback()
        logger.error(f"Batch project creation failed: {e}")
        raise

    return {
        "account_name": account_name,
        "total_requested": len(location_data),
        "total_created": len(created_projects),
        "total_failed": len(location_data) - len(created_projects),
        "results": results,
    }


def batch_update_projects(
    session: Session,
    context: UserContext,
    account_name: str,
    project_updates: List[Dict[str, Any]],
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Update multiple projects for a given account.

    Args:
        session: Database session
        context: User context for authentication
        account_name: Name of the account that owns the projects
        project_updates: List of dicts with project_id, project_params, expected_version
        auto_commit: Whether to commit changes automatically

    Returns:
        Dict containing update results
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    results = []
    updated_projects = []

    try:
        for i, project_update in enumerate(project_updates):
            project_id = project_update.get("project_id")
            project_params = project_update.get("project_params")
            expected_version = project_update.get("expected_version")

            if not project_id:
                results.append(
                    {
                        "project_id": None,
                        "project_name": f"update_{i}",
                        "success": False,
                        "error_message": "Missing project_id in update data",
                    }
                )
                continue

            try:
                if isinstance(project_id, str):
                    project_id = uuid.UUID(project_id)

                if not project_params:
                    raise ValueError("Missing project_params in update data")

                updated_project = update_project(
                    session=session,
                    context=context,
                    project_id=project_id,
                    params=project_params,
                    auto_commit=False,
                    expected_version=expected_version,
                )

                results.append(
                    {
                        "project_id": str(updated_project.id),
                        "project_name": updated_project.name,
                        "display_name": updated_project.display_name,
                        "success": True,
                        "error_message": None,
                    }
                )

                updated_projects.append(updated_project)

                logger.info(f"Successfully updated project: {updated_project.name}")

            except Exception as e:
                logger.error(f"Failed to update project {project_id}: {e}")
                results.append(
                    {
                        "project_id": str(project_id) if project_id else None,
                        "project_name": f"unknown_{i}",
                        "display_name": None,
                        "success": False,
                        "error_message": str(e),
                    }
                )

        if auto_commit:
            session.commit()
            logger.info(f"Successfully updated {len(updated_projects)} projects")
        else:
            session.flush()

    except Exception as e:
        session.rollback()
        logger.error(f"Batch project update failed: {e}")
        raise

    return {
        "account_name": account_name,
        "total_requested": len(project_updates),
        "total_updated": len(updated_projects),
        "total_failed": len(project_updates) - len(updated_projects),
        "results": results,
    }


def batch_delete_projects(
    session: Session,
    context: UserContext,
    account_name: str,
    project_ids: List[uuid.UUID],
    auto_commit: bool = True,
) -> Dict[str, Any]:
    """
    Delete multiple projects for a given account.

    Args:
        session: Database session
        context: User context for authentication
        account_name: Name of the account that owns the projects
        project_ids: List of project UUIDs to delete
        auto_commit: Whether to commit changes automatically

    Returns:
        Dict containing deletion results
    """
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    results = []
    deleted_projects = []

    try:
        for i, project_id in enumerate(project_ids):
            try:
                if isinstance(project_id, str):
                    project_id = uuid.UUID(project_id)

                project = get_project(session, project_id)
                if not project:
                    results.append(
                        {
                            "project_id": str(project_id),
                            "project_name": f"unknown_{i}",
                            "success": False,
                            "error_message": f"Project {project_id} not found",
                        }
                    )
                    continue

                if project.account.name != account_name:
                    results.append(
                        {
                            "project_id": str(project_id),
                            "project_name": project.name,
                            "success": False,
                            "error_message": f"Project {project_id} does not belong to account {account_name}",
                        }
                    )
                    continue

                project_name = project.name

                try:
                    curr_sub, _ = subscription_service.get_account_subscriptions(
                        session, project.account_id
                    )
                    if curr_sub:
                        subscription_service.remove_project_subscription(
                            session, project.id, curr_sub.external_id
                        )
                except Exception:
                    logger.error(
                        "Failed to remove project from subscription before deletion",
                        extra={
                            "project_id": str(project_id),
                            "account_id": str(project.account_id),
                        },
                        exc_info=True,
                    )
                    raise

                delete_project(
                    session=session,
                    context=context,
                    project_id=project_id,
                )

                results.append(
                    {
                        "project_id": str(project_id),
                        "project_name": project_name,
                        "success": True,
                        "error_message": None,
                    }
                )

                deleted_projects.append(project_id)

                logger.info(
                    f"Successfully deleted project: {project_name} ({project_id})"
                )

            except Exception as e:
                logger.error(f"Failed to delete project {project_id}: {e}")
                results.append(
                    {
                        "project_id": str(project_id),
                        "project_name": f"unknown_{i}",
                        "success": False,
                        "error_message": str(e),
                    }
                )

        if auto_commit:
            session.commit()
            logger.info(f"Successfully deleted {len(deleted_projects)} projects")
        else:
            session.flush()

    except Exception as e:
        session.rollback()
        logger.error(f"Batch project deletion failed: {e}")
        raise

    return {
        "account_name": account_name,
        "total_requested": len(project_ids),
        "total_deleted": len(deleted_projects),
        "total_failed": len(project_ids) - len(deleted_projects),
        "results": results,
    }


async def create_project_async(
    async_session: AsyncSession,
    context: UserContext,
    account_name: str,
    project_name: str,
    params: ProjectParams,
) -> db.Project:
    """Create a project asynchronously."""

    # validate parameters
    account = await account_service.get_account_async(async_session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")
    if not params.agent_id:
        raise ValueError("Missing agent_id in request")

    agent = await agent_service.get_agent_async(async_session, params.agent_id)
    if not agent or agent.account_id != account.id:
        raise ValueError("selected agent is not available in the account")

    account_id = account.id

    # Add API channel with project name as identifier
    api_channel_identifier = f"api:{project_name}"
    if params.channel_identifiers is None:
        params.channel_identifiers = []
    if api_channel_identifier not in params.channel_identifiers:
        params.channel_identifiers.append(api_channel_identifier)

    # Create project using async repository
    project_repository = ProjectRepositoryAsync(async_session)
    project = await project_repository.create_project(
        account_id, project_name, **asdict(params)
    )

    # Create default voice_config for the project
    voice_repo = VoiceConfigRepository(async_session)

    default_voice_id = "da69d796-4603-4419-8a95-293bfc5679eb"
    voice_config_data = VoiceConfigData(
        project_id=project.id,
        language="english",
        voice_id=default_voice_id,
        first_message=f"Hello, this is {project_name} AI Agent, how can I help you today?!",
        transfer_message="",
        speech_rate="normal",
        background_sound="",
        voice_model="sonic-2",
    )
    await voice_repo.create(voice_config_data)

    # Capture project data for change logging
    project_data_snapshot = _create_project_data_snapshot(project)

    # Schedule background logging (non-blocking) with captured project data
    asyncio.get_event_loop().run_in_executor(
        None,
        _log_project_change_sync,
        async_session.bind.sync_engine,
        context.email,
        account.id,
        project.id,
        "create",  # operation type
        project_data_snapshot,  # captured project data
    )

    return project


async def delete_project_async(
    async_session: AsyncSession,
    context: UserContext,
    project_id: uuid.UUID,
) -> None:
    """Delete a project and its voice_configs asynchronously."""
    project_repository = ProjectRepositoryAsync(async_session)

    # Check if project exists
    existing_project = await project_repository.get_project(project_id)
    if not existing_project:
        return

    project_account_id = existing_project.account_id
    project_channel_identifiers = list(existing_project.channel_identifiers or [])
    project_data_snapshot = _create_project_data_snapshot(existing_project)
    sync_engine = async_session.bind.sync_engine

    # Release phone numbers in background (fire-and-forget)
    unique_numbers = set()
    for identifier in project_channel_identifiers:
        if identifier.startswith(("sms:", "voice:", "phone:")):
            number = identifier.split(":", 1)[1]
            unique_numbers.add(number)

    if unique_numbers:
        for number in unique_numbers:
            logger.info(
                "Returning phone number to pool from project.",
                extra={
                    "project_id": project_id,
                    "phone_number": number,
                },
            )
            # Execute phone number release in thread pool (fire-and-forget)
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda n=number: _release_number_safe(n),
            )

    # Delete associated voice_configs first
    voice_repo = VoiceConfigRepository(async_session)
    deleted_voice_configs = await voice_repo.delete_by_project_id(project_id)

    logger.debug(
        f"Deleted {deleted_voice_configs} voice configs for project",
        extra={
            "project_id": str(project_id),
            "deleted_voice_configs": deleted_voice_configs,
        },
    )

    # Delete the project using async repository
    await project_repository.delete_project(project_id)

    # Schedule background logging (non-blocking) with captured project data
    asyncio.get_event_loop().run_in_executor(
        None,
        _log_project_change_sync,
        sync_engine,
        context.email,
        project_account_id,
        project_id,
        "delete",  # operation type
        project_data_snapshot,  # captured project data
    )
