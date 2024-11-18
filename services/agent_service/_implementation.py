import uuid
from typing import Any, Dict, List, Optional

from phi.agent.agent import Agent as PhiAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ai import integrate_agent
from db.repositories.account_repository import AccountRepository
from db.repositories.agent_repository import AgentRepository, AgentRepositoryAsync
from db.tables import Agent


async def get_ai_agent_async(
    db: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> PhiAgent:
    # Retrieve the agent from the database
    agent_repository = AgentRepositoryAsync(db)
    agent = await agent_repository.get_agent(agent_id=agent_id)

    if agent is None:
        raise ValueError("Invalid agent_id")

    # Assuming integrate_agent is a synchronous function
    return integrate_agent(
        agent_id=str(agent_id),
        account_name=agent.account.name,
        agent_raw_config=agent.raw_config,
        user_id=str(user_id),
        conversation_id=str(conversation_id),
        stream=stream,
    )


def get_ai_agent(
    db: Session,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> PhiAgent:
    # Retrieve the agent from the database
    agent_repository = AgentRepository(db)
    agent = agent_repository.get_agent(agent_id=agent_id)
    if agent is None:
        raise ValueError("Invalid agent_id")

    return integrate_agent(
        agent_id=str(agent_id),
        account_name=agent.account.name,
        agent_raw_config=agent.raw_config,
        user_id=str(user_id),
        conversation_id=str(conversation_id) if conversation_id else None,
        new_run=new_run,
    )


def get_agent(db: Session, agent_id: uuid.UUID) -> Optional[Agent]:
    # Retrieve the agent from the database
    agent_repository = AgentRepository(db)
    agent = agent_repository.get_agent(agent_id=agent_id)
    return agent


def get_agents_by_account(db: Session, account_name: str) -> Optional[List[Agent]]:
    # Retrieve the agent from the database
    account_repository = AccountRepository(db)
    account = account_repository.get_account(account_name)
    agents = []
    if account:
        account_id = account.id
        agents = AgentRepository(db).get_agents_by_account(account_id=account_id)
    return agents


def update_agent_config(
    db: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = AgentRepository(db)
    agent_repository.update_agent_config(agent_id=agent_id, config=config)


def replace_agent_config(
    db: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = AgentRepository(db)
    agent_repository.replace_agent_config(agent_id=agent_id, config=config)
