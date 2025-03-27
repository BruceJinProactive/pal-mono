import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.agent import Agent, CreateAgentRequest, UpdateAgentRequest
from services import agent_service

from ._auth import authorize_user_account
from ._builder import build_agent
from ._utils import UserContext


def get_agent(
    agent_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> Agent:
    agent = agent_service.get_agent(session, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    authorize_user_account(context, agent.account.name)
    return build_agent(agent)


async def create_agent(
    create_request: CreateAgentRequest,
    context: UserContext,
    session: Session,
) -> Agent:
    authorize_user_account(context, create_request.account_name)
    agent_params = agent_service.AgentParams(
        name=create_request.name,
        description=create_request.description,
        communication_style=create_request.communication_style,
        interaction_guidelines=create_request.interaction_guidelines,
        raw_config=create_request.raw_config,
    )
    try:
        db_agent = agent_service.create_agent(
            session, create_request.account_name, agent_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_agent(db_agent)


async def update_agent(
    agent_id: uuid.UUID,
    update_request: UpdateAgentRequest,
    context: UserContext,
    session: Session,
) -> Agent:
    agent = agent_service.get_agent(session, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
            headers={"Content-Type": "application/json"},
        )
    authorize_user_account(context, agent.account.name)
    agent_params = agent_service.AgentParams(
        name=update_request.name,
        description=update_request.description,
        communication_style=update_request.communication_style,
        interaction_guidelines=update_request.interaction_guidelines,
        raw_config=update_request.raw_config,
    )
    try:
        db_agent = agent_service.update_agent(session, agent_id, agent_params)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_agent(db_agent)
