import uuid

from agno.agent.agent import Agent as AgnoAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import _implementation


def get_ai_agent(
    session: Session,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> AgnoAgent:
    """
    Retrieve a AgnoAgent instance based on the provided agent ID, user ID, conversation ID, and project ID.

    Args:
        session (Session): The database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        project_id (uuid.UUID): The unique identifier of the project.
        conversation_id (uuid.UUID | None, optional): The unique identifier of the conversation. Defaults to None.
        new_run (bool, optional): If True, starts a new run. If False, attempts to continue from the last run. Defaults to False.

    Returns:
        AgnoAgent: The retrieved AgnoAgent instance.
    """
    return _implementation.get_ai_agent(
        session,
        agent_id,
        user_id,
        project_id,
        conversation_id,
        new_run=new_run,
    )


async def get_ai_agent_async(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    stream: bool = False,
) -> AgnoAgent:
    """
    Retrieve a AgnoAgent instance based on the provided agent ID, user ID, conversation ID, and project ID.

    Args:
        session (AsyncSession): The asynchronous database session to use for the query.
        agent_id (uuid.UUID): The unique identifier of the agent.
        user_id (uuid.UUID): The unique identifier of the user.
        project_id (uuid.UUID): The unique identifier of the project.
        conversation_id (uuid.UUID): The unique identifier of the conversation.
        stream (bool, optional): If True, enables streaming mode for the agent. Defaults to False.

    Returns:
        AgnoAgent: The retrieved AgnoAgent instance.
    """
    return await _implementation.get_ai_agent_async(
        session,
        agent_id,
        user_id,
        project_id,
        conversation_id=conversation_id,
        stream=stream,
    )
