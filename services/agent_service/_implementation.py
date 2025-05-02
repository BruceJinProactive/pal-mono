import uuid
from dataclasses import asdict
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import AgentConfig
from utils.log import logger

from .. import account_service
from . import _raw_config
from .schema import AgentParams


async def construct_agent_config(
    db_session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> AgentConfig:
    """
    Builds an Agent Config based on the Raw Config.

    Args:
        db_session (AsyncSession): The database session.
        agent_id (uuid.UUID): The agent id.
        user_id (uuid.UUID): The user id.
        project_id (uuid.UUID): The project id.
        conversation_id (uuid.UUID): The conversation (session) id of the user-agent interaction.

    Raises:
        ValueError: If the agent_id or project_id is invalid.

    Returns:
        AgentConfig: The agent configuration object.
    """

    # Retrieve the agent from the database
    agent_repository = db.AgentRepositoryAsync(db_session)
    db_agent = await agent_repository.get_agent(agent_id=agent_id)
    if db_agent is None:
        raise ValueError("Invalid agent_id")

    # Retrieve the project from the database
    project_repository = db.ProjectRepositoryAsync(db_session)
    db_project = await project_repository.get_project(project_id)
    if db_project is None:
        raise ValueError("Invalid project_id")

    raw_config = _raw_config.RawConfig(
        agent_id=agent_id,
        agent_raw_config=db_agent.raw_config,
        project_raw_config=db_project.raw_config,
        account_id=db_agent.account.id,
        account_name=db_agent.account.name,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    # Convert blueprint to agent config
    logger.debug("Loading agent config...")
    return raw_config.build()


def get_agent(session: Session, agent_id: uuid.UUID) -> Optional[db.Agent]:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepository(session)
    agent = agent_repository.get_agent(agent_id=agent_id)
    return agent


def replace_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = db.AgentRepository(session)
    agent_repository.replace_agent_config(agent_id=agent_id, config=config)


def create_agent(
    session: Session, account_name: str, params: AgentParams, auto_commit: bool
) -> db.Agent:
    # Create an agent for the given account
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")
    agent_repository = db.AgentRepository(session, auto_commit)
    agent = agent_repository.create_agent(account.id, **asdict(params))
    return agent


def update_agent(
    session: Session, agent_id: uuid.UUID, params: AgentParams
) -> db.Agent:
    # Update the specified agent with the provided params
    agent_repository = db.AgentRepository(session)
    agent = agent_repository.update_agent(agent_id, **asdict(params))
    if agent is None:
        raise ValueError(f"Agent with id {agent_id} not found")
    return agent


def delete_agent(session: Session, agent_id: uuid.UUID):
    agent_repository = db.AgentRepository(session)
    agent_repository.delete_agent(agent_id)
