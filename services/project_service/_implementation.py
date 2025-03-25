import uuid
from dataclasses import asdict
from typing import Any, Dict, List

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.chat.message import Message

from .. import account_service, agent_service
from .schema import ProjectParams


def create_project(
    session: Session, account_name: str, project_name: str, params: ProjectParams
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
    project_repository = db.ProjectRepository(session)
    try:
        project = project_repository.create_project(
            account.id, project_name, **asdict(params)
        )
    except (SQLAlchemyError, IntegrityError):
        raise ValueError("duplicate record not allowed")
    return project


def update_project(
    session: Session, project_id: uuid.UUID, params: ProjectParams
) -> db.Project:
    project_repository = db.ProjectRepository(session)
    project = project_repository.update_project(project_id, **asdict(params))
    return project


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


def delete_project(session: Session, project_id: uuid.UUID) -> None:
    project_repository = db.ProjectRepository(session)
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
