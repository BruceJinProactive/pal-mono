import copy
import uuid
from dataclasses import asdict
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from api.schemas.chat.message import Message
from db.tables.change_log import ChangeResourceType
from utils.log import logger

from .. import account_service, agent_service, history_service
from .schema import ProjectParams


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

    project_repository = db.ProjectRepository(session, auto_commit=False)

    try:
        project = project_repository.create_project(
            account.id, project_name, **asdict(params)
        )
        history_service.create_change_log(
            session=session,
            account_id=account.id,
            resource_type=ChangeResourceType.Project,
            resource_id=str(project.id),
            author=context.email,
            old_record=None,
            new_record=project,
        )
        if auto_commit:
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create project due to error: {e}")
        raise
    return project


def update_project(
    session: Session,
    context: UserContext,
    project_id: uuid.UUID,
    params: ProjectParams,
) -> db.Project:
    project_repository = db.ProjectRepository(session, auto_commit=False)

    existing_project = project_repository.get_project(project_id)
    if not existing_project:
        raise ValueError(f"Project {project_id} does not exist.")

    try:
        old_project = copy.copy(existing_project)
        updated_project = project_repository.update_project(
            project_id, **asdict(params)
        )
        history_service.create_change_log(
            session=session,
            account_id=existing_project.account.id,
            resource_type=ChangeResourceType.Project,
            resource_id=str(project_id),
            author=context.email,
            old_record=old_project,
            new_record=updated_project,
        )
        session.commit()
        return updated_project
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update project due to error: {e}")
        raise


def get_project(session: Session, project_id: uuid.UUID):
    project_repository = db.ProjectRepository(session)
    return project_repository.get_project(project_id)


def get_project_by_name(session: Session, project_name: str):
    project_repository = db.ProjectRepository(session)
    return project_repository.get_project_by_name(project_name)


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

    existing_project = project_repository.get_project(project_id)
    if not existing_project:
        return

    try:
        project_repository.delete_project(project_id)
        history_service.create_change_log(
            session=session,
            account_id=existing_project.account.id,
            resource_type=ChangeResourceType.Project,
            resource_id=str(existing_project.id),
            author=context.email,
            old_record=existing_project,
            new_record=None,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete project due to error: {e}")
        raise


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
