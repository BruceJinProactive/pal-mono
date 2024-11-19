import uuid
from typing import Any, Dict, List, Optional

from phi.agent.agent import Agent as PhiAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db

from . import _implementation


async def get_ai_agent_async(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> PhiAgent:
    """
    Retrieve a PhiAgent instance based on the provided agent ID, user ID, and conversation ID.

    Args:
        session (AsyncSession): The asynchronous database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        conversation_id (uuid.UUID): The unique identifier of the conversation.

    Returns:
        PhiAgent: The retrieved PhiAgent instance.
    """
    return await _implementation.get_ai_agent_async(
        session, agent_id, user_id, conversation_id=conversation_id, stream=stream
    )


def get_ai_agent(
    session: Session,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> PhiAgent:
    """
    Retrieve a PhiAgent instance based on the provided agent ID and user ID.

    Args:
        session (Session): The database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        new_run (bool, optional): Flag indicating whether this is a new run. Defaults to False.

    Returns:
        PhiAgent: The retrieved PhiAgent instance.
    """
    return _implementation.get_ai_agent(
        session, agent_id, user_id, conversation_id, new_run=new_run
    )


def get_agent(session: Session, agent_id: uuid.UUID) -> Optional[db.Agent]:
    """
    Retrieve an Agent instance based on the provided agent ID.

    Args:
        session (Session): The database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.

    Returns:
        Optional[Agent]: The retrieved Agent instance if found, otherwise None.
    """
    return _implementation.get_agent(session, agent_id)


def get_agents_by_account(
    session: Session, account_name: str
) -> Optional[List[db.Agent]]:
    """
    Retrieve a list of Agents instance based on the provided agent ID.

    Args:
        session (Session): The database session to use for the query.
        account_name (str): The unique identifier of the agent.

    Returns:
        Optional[List[Agent]]: Return the list of agents if found, otherwise None
    """
    return _implementation.get_agents_by_account(session, account_name)


def update_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Update the raw_config of the agent associated with the provided agent ID.

    Args:
        session (Session): The database session to use for the update.
        agent_id (uuid.UUID): The unique identifier of the agent.
        config (Dict[str, Any]): A dictionary containing the configuration settings to update.

    Returns:
        None
    """
    return _implementation.update_agent_config(session, agent_id, config)


def replace_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Replace the raw_config of the agent associated with the provided agent ID.

    Args:
        session (Session): The database session to use for the update.
        agent_id (uuid.UUID): The unique identifier of the agent.
        config (Dict[str, Any]): A dictionary containing the new configuration settings.

    Returns:
        None
    """
    return _implementation.replace_agent_config(session, agent_id, config)


__all__ = [
    "get_ai_agent",
    "get_agent",
    "get_agents_by_account",
    "update_agent_config",
    "replace_agent_config",
]
