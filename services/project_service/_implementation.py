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
from services.history_service import change_log_context

from .. import account_service, agent_service
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
) -> db.Project:
    project_repository = db.ProjectRepository(session, auto_commit=False)

    existing_project = project_repository.get_project(project_id)
    if not existing_project:
        raise ValueError(f"Project {project_id} does not exist.")

    old_project = copy.copy(existing_project)

    api_channel_identifier = f"api:{existing_project.name}"
    if params.channel_identifiers is None:
        params.channel_identifiers = []
    if api_channel_identifier not in params.channel_identifiers:
        params.channel_identifiers.append(api_channel_identifier)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=existing_project.account.id,
        resource_id=str(project_id),
        old_record=old_project,
    ) as ctx:
        updated_project = project_repository.update_project(
            project_id, **asdict(params)
        )
        ctx.new_record = updated_project
        return updated_project


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

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Project,
        author=context.email,
        account_id=existing_project.account.id,
        resource_id=str(existing_project.id),
        old_record=existing_project,
    ):
        project_repository.delete_project(project_id)


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
