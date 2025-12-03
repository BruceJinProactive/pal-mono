import copy
import uuid
from dataclasses import asdict
from typing import Any, Dict, Optional

from pal_agents import Spec
from pal_agents.spec import PromptSpec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import AgentConfig
from db.tables.change_log import ChangeResourceType
from db.tables.types import Channel, IntegrationType
from services import account_service, integration_service
from services.auth_types import UserContext
from services.history_service import change_log_context
from utils.log import logger

from . import _raw_config
from .schema import AgentParams


async def construct_agent_spec() -> Spec:
    """Build a pal_agents.Spec with hardcoded instructions for testing."""
    return Spec(
        prompt=PromptSpec(
            instructions="You are a helpful assistant. Respond concisely and helpfully to user messages."
        )
    )


async def construct_agent_config(
    db_session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel: Channel,
    sender_identifier: str | None = None,
) -> AgentConfig:
    """
    Builds an Agent Config based on the Raw Config.

    Args:
        db_session (AsyncSession): The database session.
        agent_id (uuid.UUID): The agent id.
        user_id (uuid.UUID): The user id.
        project_id (uuid.UUID): The project id.
        conversation_id (uuid.UUID): The conversation (session) id of the user-agent interaction.
        channel (Channel): For which comm channel should this agent config build for, e.g. sms, voice
        sender_identifier (str | None): The sender identifier (phone for voice/sms, user ID for other channels) (optional).

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

    integration = await integration_service.async_get_integration_by_project_and_type(
        db_session, db_project.account_id, db_project.id, IntegrationType.pos
    )

    result = await db_session.execute(
        select(db.ProjectIntegration).filter(
            db.ProjectIntegration.project_id == db_project.id
        )
    )
    project_integrations = list(result.scalars())

    # Fetch FAQs for the account and project (combined)
    faq_result = await db_session.execute(
        select(db.FAQ)
        .filter(db.FAQ.account_id == db_agent.account.id)
        .filter((db.FAQ.project_id.is_(None)) | (db.FAQ.project_id == project_id))
        .order_by(db.FAQ.project_id.is_(None).desc())
    )
    faqs = list(faq_result.scalars())

    raw_config = _raw_config.RawConfig(
        agent=db_agent,
        project=db_project,
        account=db_agent.account,
        user_id=user_id,
        conversation_id=conversation_id,
        channel=channel,
        integration=integration,
        sender_identifier=sender_identifier,
        project_integrations=project_integrations,
        faqs=faqs,
    )

    # Convert blueprint to agent config
    logger.debug("Loading agent config...")
    return raw_config.build()


async def get_agent_async(
    async_session: AsyncSession, agent_id: uuid.UUID
) -> Optional[db.Agent]:
    """Retrieve an agent by ID asynchronously."""
    agent_repository = db.AgentRepositoryAsync(async_session)
    agent = await agent_repository.get_agent(agent_id=agent_id)
    return agent


def get_agent(session: Session, agent_id: uuid.UUID) -> Optional[db.Agent]:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepository(session)
    agent = agent_repository.get_agent(agent_id=agent_id)
    return agent


def replace_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = db.AgentRepository(session)
    agent_repository.replace_agent_config(agent_id=agent_id, config=config)


def create_agent(
    session: Session,
    context: UserContext,
    account_name: str,
    params: AgentParams,
    auto_commit: bool,
) -> db.Agent:
    # Create an agent for the given account
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")
    agent_repository = db.AgentRepository(session, auto_commit=False)

    agent_params = asdict(params)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Agent,
        author=context.email,
        account_id=account.id,
        auto_commit=auto_commit,
    ) as ctx:
        agent = agent_repository.create_agent(account.id, **agent_params)
        ctx.resource_id = str(agent.id)
        ctx.new_record = agent

    return agent


def update_agent(
    session: Session,
    context: UserContext,
    agent_id: uuid.UUID,
    params: AgentParams,
    expected_version: int | None = None,
) -> db.Agent:
    # Update the specified agent with the provided params
    agent_repository = db.AgentRepository(session)

    existing_agent = agent_repository.get_agent(agent_id)
    if not existing_agent:
        raise ValueError(f"Agent with id {agent_id} not found")

    old_agent = copy.copy(existing_agent)

    agent_params = asdict(params)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Agent,
        author=context.email,
        account_id=existing_agent.account.id,
        resource_id=str(agent_id),
        old_record=old_agent,
    ) as ctx:
        new_agent = agent_repository.update_agent(
            agent_id, expected_version, **agent_params
        )
        if new_agent is None:
            raise ValueError(f"Failed to update agent {agent_id}")
        ctx.new_record = new_agent
        return new_agent


def delete_agent(session: Session, context: UserContext, agent_id: uuid.UUID):
    agent_repository = db.AgentRepository(session, auto_commit=False)

    existing_agent = agent_repository.get_agent(agent_id)
    if not existing_agent:
        return

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Agent,
        author=context.email,
        account_id=existing_agent.account.id,
        resource_id=str(existing_agent.id),
        old_record=existing_agent,
    ):
        agent_repository.delete_agent(agent_id)
