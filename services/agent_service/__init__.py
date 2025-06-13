import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import AgentConfig
from api.routes.admin import UserContext
from db.tables.types import Channel
from utils.dd import traced

from . import _implementation
from .schema import AgentParams


@traced("Agent Service Constructing Config")
async def construct_agent_config(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel: Channel,
) -> AgentConfig:
    return await _implementation.construct_agent_config(
        session,
        agent_id,
        user_id,
        project_id,
        conversation_id,
        channel,
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


def create_agent(
    session: Session,
    context: UserContext,
    account_name: str,
    params: AgentParams,
    auto_commit: bool = True,
) -> db.Agent:
    """
    Creates a new agent for the specified account using provided parameters and saves
    it in the database.

    Args
        session (Session): A database session used for executing the transaction.
        account_name (str): Name of the account to which the agent belongs.
        params (AgentParams): Agent parameters to be used for creating the agent.
        auto_commit (bool): New agent will be committed automatically if True.

    Returns:
        Agent: The database model object representing the created agent.
    """
    return _implementation.create_agent(
        session, context, account_name, params, auto_commit
    )


def update_agent(
    session: Session,
    context: UserContext,
    agent_id: uuid.UUID,
    params: AgentParams,
) -> db.Agent:
    """
    Update the specified agent with the parameters provided

    Args
        session (Session): A database session used for executing the transaction.
        agent_id (uuid.UUID): UUID of the agent to update
        params (AgentParams): Agent parameters that need to be updated.

    Returns:
        Agent: The database model object representing the updated agent.
    """
    return _implementation.update_agent(session, context, agent_id, params)


def delete_agent(
    session: Session,
    context: UserContext,
    agent_id: uuid.UUID,
):
    """
    Delete the specified agent, if agent_id does not exist, this is a no-op.
    """
    _implementation.delete_agent(session, context, agent_id)


__all__ = [
    "get_agent",
    "replace_agent_config",
    "create_agent",
    "update_agent",
    "delete_agent",
]
