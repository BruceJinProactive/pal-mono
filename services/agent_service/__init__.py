import uuid
from typing import Any, Dict, List, Optional

from phi.agent.agent import Agent as PhiAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import Assistant

from . import _implementation


async def get_ai_agent_async(
    db: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> PhiAgent:
    """
    Retrieve a PhiAgent instance based on the provided agent ID, user ID, and conversation ID.

    Args:
        db (AsyncSession): The asynchronous database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        conversation_id (uuid.UUID): The unique identifier of the conversation.

    Returns:
        PhiAgent: The retrieved PhiAgent instance.
    """
    return await _implementation.get_ai_agent_async(
        db, agent_id, user_id, conversation_id=conversation_id
    )


def get_ai_agent(
    db: Session,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> PhiAgent:
    """
    Retrieve a PhiAgent instance based on the provided agent ID and user ID.

    Args:
        db (Session): The database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        new_run (bool, optional): Flag indicating whether this is a new run. Defaults to False.

    Returns:
        PhiAgent: The retrieved PhiAgent instance.
    """
    return _implementation.get_ai_agent(
        db, agent_id, user_id, conversation_id, new_run=new_run
    )


def get_agent(db: Session, agent_id: uuid.UUID) -> Optional[Assistant]:
    """
    Retrieve an Agent instance based on the provided agent ID.

    Args:
        db (Session): The database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.

    Returns:
        Optional[Assistant]: The retrieved Agent instance if found, otherwise None.
    """
    return _implementation.get_agent(db, agent_id)


def get_agents_by_account(db: Session, account_name: str) -> Optional[List[Assistant]]:
    """
    Retrieve a list of Assistants instance based on the provided agent ID.

    Args:
        db (Session): The database session to use for the query.
        account_name (str): The unique identifier of the agent.

    Returns:
        Optional[List[Assistant]]: Return the list of agents if found, otherwise None
    """
    return _implementation.get_agents_by_account(db, account_name)


def update_agent_config(
    db: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Update the raw_config of the agent associated with the provided agent ID.

    Args:
        db (Session): The database session to use for the update.
        agent_id (uuid.UUID): The unique identifier of the agent.
        config (Dict[str, Any]): A dictionary containing the configuration settings to update.

    Returns:
        None
    """
    return _implementation.update_agent_config(db, agent_id, config)


def replace_agent_config(
    db: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Replace the raw_config of the agent associated with the provided agent ID.

    Args:
        db (Session): The database session to use for the update.
        agent_id (uuid.UUID): The unique identifier of the agent.
        config (Dict[str, Any]): A dictionary containing the new configuration settings.

    Returns:
        None
    """
    return _implementation.replace_agent_config(db, agent_id, config)


__all__ = [
    "get_ai_agent",
    "get_agent",
    "get_agents_by_account",
    "update_agent_config",
    "replace_agent_config",
]
