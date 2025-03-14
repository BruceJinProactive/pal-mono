import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from api.schemas.admin.agent import Agent, CreateAgentRequest, UpdateAgentRequest
from services import agent_service

from . import _auth
from ._builder import build_agent
from ._utils import UserContext


def get_agent(agent_id: uuid.UUID, context: UserContext, session: Session) -> Agent:
    agent = agent_service.get_agent(session, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    _auth.authorize_user_account(context, agent.account.name)
    return build_agent(agent)


async def create_agent(request: Request, session: Session) -> Agent:
    agent_data = await request.json()
    create_request = CreateAgentRequest(**agent_data)
    agent_params = agent_service.AgentParams(
        name=create_request.name,
        description=create_request.description,
        communication_style=create_request.communication_style,
        interaction_guidelines=create_request.interaction_guidelines,
        raw_config=create_request.raw_config,
    )
    try:
        db_agent = agent_service.create_agent(
            session, create_request.account_id, agent_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_agent(db_agent)


async def update_agent(
    request: Request, agent_id: uuid.UUID, session: Session
) -> Agent:
    agent_data = await request.json()
    update_request = UpdateAgentRequest(**agent_data)
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
