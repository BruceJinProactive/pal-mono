import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._builder import build_prompt, build_prompt_details
from api.routes.admin._utils import UserContext
from api.schemas.admin.prompt import (
    CreatePromptRequest,
    Prompt,
    PromptDetails,
    SystemPrompt,
    UpdatePromptRequest,
)
from db.tables.types import AgentType, Channel, TargetTier
from services import (
    account_service,
    agent_service,
    project_service,
    prompt_service,
    subscription_service,
)
from services.agent_service.prompts import prompt_factory
from services.prompt_service.schema import PromptParams


def create_prompt(
    context: UserContext,
    session: Session,
    account_name: str,
    request: CreatePromptRequest,
) -> Prompt:
    authorize_admin(context)
    prompt_params = PromptParams(
        name=request.name,
        channel=request.channel,
        default_prompt_id=request.default_prompt_id,
        resource_id=request.resource_id,
        resource_type=request.resource_type,
        content=request.content,
        change_summary=request.change_summary,
    )

    try:
        db_prompt = prompt_service.create_prompt(
            session,
            context,
            account_name,
            prompt_params,
            auto_commit=True,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    return build_prompt(db_prompt, session)


def get_prompts(
    context: UserContext,
    session: Session,
    account_name: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    search: str | None = None,
    channels: list[str] | None = None,
) -> list[Prompt]:
    authorize_admin(context)
    try:
        db_prompts = prompt_service.get_prompts(
            session,
            context,
            account_name,
            resource_type,
            resource_id,
            search,
            channels,
            auto_commit=True,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    return [build_prompt(db_prompt, session) for db_prompt in db_prompts]


def update_prompt(
    context: UserContext,
    session: Session,
    account_name: str,
    prompt_id: uuid.UUID,
    request: UpdatePromptRequest,
) -> Prompt:
    authorize_admin(context)
    try:
        db_prompt = prompt_service.update_prompt(
            session,
            context,
            account_name,
            prompt_id,
            name=request.name,
            default_prompt_id=request.default_prompt_id,
            channel=request.channel,
            content=request.content,
            change_summary=request.change_summary,
            auto_commit=True,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    return build_prompt(db_prompt, session)


def get_prompt_versions(
    context: UserContext,
    session: Session,
    account_name: str,
    prompt_id: uuid.UUID,
) -> list[PromptDetails]:
    authorize_admin(context)
    try:
        db_versions = prompt_service.get_prompt_versions(
            session,
            context,
            account_name,
            prompt_id,
            auto_commit=True,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )

    return [build_prompt_details(version) for version in db_versions]


def delete_prompt(
    context: UserContext,
    session: Session,
    account_name: str,
    prompt_id: uuid.UUID,
) -> None:
    authorize_admin(context)
    try:
        prompt_service.delete_prompt(
            session,
            context,
            account_name,
            prompt_id,
            auto_commit=True,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )


def get_system_prompts(
    context: UserContext,
    session: Session,
    account_name: str,
    resource_type: str,
    resource_id: uuid.UUID,
    search: str | None = None,
    channels: str | None = None,
) -> list[SystemPrompt]:
    authorize_admin(context)
    account = account_service.get_account(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
        )

    agent_type = None
    if resource_type == "project":
        try:
            project = project_service.get_project(session, resource_id)
            if project and project.agent_id:
                agent = agent_service.get_agent(session, project.agent_id)
                if agent and agent.agent_type:
                    agent_type = AgentType(agent.agent_type)
        except Exception:
            pass
    elif resource_type == "agent":
        try:
            agent = agent_service.get_agent(session, resource_id)
            if agent and agent.agent_type:
                agent_type = AgentType(agent.agent_type)
        except Exception:
            pass

    plan_tier = None
    try:
        current_subscription, _ = subscription_service.get_account_subscriptions(
            session, account.id
        )
        if (
            current_subscription
            and current_subscription.subscription_plan
            and current_subscription.subscription_plan.tier
        ):
            plan_tier = TargetTier(current_subscription.subscription_plan.tier)
    except Exception:
        pass

    channel_filter = None
    if channels:
        channel_filter = []
        for channel_str in channels.split(","):
            channel_str = channel_str.strip().lower()
            for channel_enum in Channel:
                if channel_enum.value == channel_str:
                    channel_filter.append(channel_enum)
                    break

    filtered_prompts = []
    for prompt in prompt_factory.registry:
        if prompt.agent_types is not None:
            if agent_type is None or agent_type not in prompt.agent_types:
                continue

        if prompt.plan_tiers is not None:
            if plan_tier is None or plan_tier not in prompt.plan_tiers:
                continue

        if channel_filter is not None:
            if prompt.channels is None:
                continue
            if not any(channel in prompt.channels for channel in channel_filter):
                continue

        if search is not None:
            search_lower = search.lower()
            if (
                search_lower not in prompt.title.lower()
                and search_lower not in prompt.instructions.lower()
            ):
                continue

        system_prompt = SystemPrompt(
            id=prompt.id,
            title=prompt.title,
            instructions=prompt.instructions,
            channels=(
                [channel.value for channel in prompt.channels]
                if prompt.channels
                else None
            ),
            agent_types=(
                [agent_type.value for agent_type in prompt.agent_types]
                if prompt.agent_types
                else None
            ),
            plan_tiers=(
                [tier.value for tier in prompt.plan_tiers]
                if prompt.plan_tiers
                else None
            ),
            pos_vendors=(
                [vendor.value for vendor in prompt.pos_vendors]
                if prompt.pos_vendors
                else None
            ),
        )
        filtered_prompts.append(system_prompt)

    return filtered_prompts
