import uuid
from typing import Any, Dict, List, Optional

from phi.agent.agent import Agent as PhiAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import (
    AgentConfig,
    AgentMetadata,
    AgentPersona,
    KnowledgeConfig,
    MemoryConfig,
    ModelConfig,
    ToolConfig,
)
from agent.legacy import integrate_agent


async def construct_agent_config(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> AgentConfig:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepositoryAsync(session)
    db_agent = await agent_repository.get_agent(agent_id=agent_id)
    if db_agent is None:
        raise ValueError("Invalid agent_id")

    # Retrieve the project from the database
    project_repository = db.ProjectRepositoryAsync(session)
    db_project = await project_repository.get_project(project_id)
    if db_project is None:
        raise ValueError("Invalid project_id")

    # Sample agent config
    config = AgentConfig(
        persona=AgentPersona(
            name="Anna",
            role="Coffee Barista",
            description="Anna is 24 years old. She is from Southern California. She went to collage in SolCal and is now studying LSAT to go to law school next year.",
        ),
        model=ModelConfig(
            identifier="medium",
            stream=stream,
        ),
        memory=MemoryConfig(
            enabled=True,
            identifier=db_agent.account.name,
            instruction="Don't remember user's gender",
        ),
        knowledge=KnowledgeConfig(
            enabled=True,
            identifier=db_agent.account.name,
        ),
        tool=ToolConfig(
            identifiers=["calculator_tool"],
        ),
        metadata=AgentMetadata(
            account_name=db_agent.account.name,
            agent_id=str(agent_id),
            user_id=str(user_id),
            session_id=str(conversation_id),
            framework="phidata",
        ),
    )

    return config


async def get_ai_agent_async(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> PhiAgent:
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
) -> PhiAgent:
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
