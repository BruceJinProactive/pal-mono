import uuid
from typing import Any, Dict, List, Optional

from agno.agent.agent import Agent as AgnoAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import AgentConfig
from agent.legacy import integrate_agent
from utils.log import logger

from . import _configs, _raw_config


async def construct_agent_config(
    db_session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> AgentConfig:
    """
    Builds an Agent Config based on the Raw Config.

    Args:
        db_session (AsyncSession): The database session.
        agent_id (uuid.UUID): The agent id.
        user_id (uuid.UUID): The user id.
        project_id (uuid.UUID): The project id.
        conversation_id (uuid.UUID): The conversation (session) id of the user-agent interaction.
        stream (bool, optional): Wether to stream the agent's response. Defaults to False.

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
        stream=stream,
    )

    # Convert blueprint to agent config
    if db_agent.account.name == "windsor":
        logger.info("Loading Windsor config...")
        return _configs.WINDSOR_CONFIG
    elif db_agent.account.name == "new-pizzamyheart":
        logger.info("Loading New PizzaMyHeart config...")
        return raw_config.build()
    else:
        logger.info("Loading Anna config...")
        return _configs.ANNA_CONFIG


async def get_ai_agent_async(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> AgnoAgent:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepositoryAsync(session)
    agent = await agent_repository.get_agent(agent_id=agent_id)

    if agent is None:
        raise ValueError("Invalid agent_id")

    # Retrieve the project from the database
    project_repository = db.ProjectRepositoryAsync(session)
    project = await project_repository.get_project(project_id)

    if project is None:
        raise ValueError("Invalid project_id")

    # Assuming integrate_agent is a synchronous function
    return integrate_agent(
        agent_id=str(agent_id),
        account_name=agent.account.name,
        agent_raw_config=agent.raw_config,
        project_raw_config=project.raw_config,
        user_id=str(user_id),
        conversation_id=str(conversation_id),
        stream=stream,
    )


def get_ai_agent(
    session: Session,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> AgnoAgent:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepository(session)
    agent = agent_repository.get_agent(agent_id=agent_id)
    if agent is None:
        raise ValueError("Invalid agent_id")

    # Retrieve the project from the database
    project_repository = db.ProjectRepository(session)
    project = project_repository.get_project(project_id)
    if project is None:
        raise ValueError("Invalid project_id")

    return integrate_agent(
        agent_id=str(agent_id),
        account_name=agent.account.name,
        agent_raw_config=agent.raw_config,
        project_raw_config=project.raw_config,
        user_id=str(user_id),
        conversation_id=str(conversation_id) if conversation_id else None,
        new_run=new_run,
    )


def get_agent(session: Session, agent_id: uuid.UUID) -> Optional[db.Agent]:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepository(session)
    agent = agent_repository.get_agent(agent_id=agent_id)
    return agent


def get_agents_by_account(
    session: Session, account_name: str
) -> Optional[List[db.Agent]]:
    # Retrieve the agent from the database
    account_repository = db.AccountRepository(session)
    account = account_repository.get_account(account_name)
    agents = []
    if account:
        account_id = account.id
        agents = db.AgentRepository(session).get_agents_by_account(
            account_id=account_id
        )
    return agents


def update_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = db.AgentRepository(session)
    agent_repository.update_agent_config(agent_id=agent_id, config=config)


def replace_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = db.AgentRepository(session)
    agent_repository.replace_agent_config(agent_id=agent_id, config=config)
