import uuid
from typing import Any, Dict, List, Optional

from phi.agent.agent import Agent as PhiAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import Assistant

from . import _implementation


async def get_ai_agent_async(
    db: AsyncSession,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> PhiAgent:
    """
    Retrieve a PhiAgent instance based on the provided agent ID, user ID, and conversation ID.

    Args:
        db (AsyncSession): The asynchronous database session to use for the query.
        assistant_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        conversation_id (uuid.UUID): The unique identifier of the conversation.

    Returns:
        PhiAgent: The retrieved PhiAgent instance.
    """
    return await _implementation.get_ai_agent_async(
        db, assistant_id, user_id, conversation_id=conversation_id
    )


def get_ai_agent(
    db: Session,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> PhiAgent:
    """
    Retrieve a PhiAgent instance based on the provided assistant ID and user ID.

    Args:
        db (Session): The database session to use for the query.
        assistant_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        new_run (bool, optional): Flag indicating whether this is a new run. Defaults to False.

    Returns:
        PhiAgent: The retrieved PhiAgent instance.
    """
    return _implementation.get_ai_agent(
        db, assistant_id, user_id, conversation_id, new_run=new_run
    )


def get_assistant(db: Session, assistant_id: uuid.UUID) -> Optional[Assistant]:
    """
    Retrieve an Agent instance based on the provided assistant ID.

    Args:
        db (Session): The database session to use for the query.
        assistant_id (uuid.UUID): The unique identifier of the agent.

    Returns:
        Optional[Assistant]: The retrieved Agent instance if found, otherwise None.
    """
    return _implementation.get_assistant(db, assistant_id)


def get_assistants_by_account(
    db: Session, account_name: str
) -> Optional[List[Assistant]]:
    """
    Retrieve a list of Assistants instance based on the provided assistant ID.

    Args:
        db (Session): The database session to use for the query.
        account_name (str): The unique identifier of the assistant.

    Returns:
        Optional[List[Assistant]]: Return the list of assistants if found, otherwise None
    """
    return _implementation.get_assistants_by_account(db, account_name)


def update_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Update the raw_config of the assistant associated with the provided assistant ID.

    Args:
        db (Session): The database session to use for the update.
        assistant_id (uuid.UUID): The unique identifier of the assistant.
        config (Dict[str, Any]): A dictionary containing the configuration settings to update.

    Returns:
        None
    """
    return _implementation.update_assistant_config(db, assistant_id, config)


def replace_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Replace the raw_config of the assistant associated with the provided assistant ID.

    Args:
        db (Session): The database session to use for the update.
        assistant_id (uuid.UUID): The unique identifier of the assistant.
        config (Dict[str, Any]): A dictionary containing the new configuration settings.

    Returns:
        None
    """
    return _implementation.replace_assistant_config(db, assistant_id, config)


__all__ = [
    "get_ai_agent",
    "get_assistant",
    "get_assistants_by_account",
    "update_assistant_config",
    "replace_assistant_config",
]
