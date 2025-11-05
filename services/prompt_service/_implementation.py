import uuid
from dataclasses import asdict

from sqlalchemy.orm import Session

import db
from db.repositories.prompt_repository import PromptRepository
from db.tables.change_log import ChangeResourceType
from services import account_service, agent_service, project_service
from services.auth_types import UserContext
from services.history_service import change_log_context
from services.prompt_service.schema import PromptDetailsParams, PromptParams


def create_prompt(
    session: Session,
    context: UserContext,
    account_name: str,
    params: PromptParams,
    auto_commit: bool,
) -> db.Prompt:
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    if not params.resource_id:
        raise ValueError("Missing resource_id in request")
    if not params.resource_type:
        raise ValueError("Missing resource_type in request")

    if params.resource_type == "project":
        project = project_service.get_project(session, params.resource_id)
        if not project or project.account_id != account.id:
            raise ValueError("Selected project is not available in the account")

    elif params.resource_type == "agent":
        agent = agent_service.get_agent(session, params.resource_id)
        if not agent or agent.account_id != account.id:
            raise ValueError("Selected agent is not available in the account")

    else:
        raise ValueError(f"Unsupported resource type: {params.resource_type}")

    if not params.content:
        raise ValueError("Missing content for initial prompt version")

    prompt_repository = PromptRepository(session, auto_commit=auto_commit)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Prompt,
        author=context.email,
        account_id=account.id,
        auto_commit=auto_commit,
    ) as ctx:
        prompt_params = asdict(params)
        content = prompt_params.pop("content", "")
        change_summary = prompt_params.pop("change_summary", None)

        prompt = prompt_repository.create_prompt(**prompt_params)
        ctx.resource_id = str(prompt.id)
        ctx.new_record = prompt

        details_params = PromptDetailsParams(
            prompt_id=prompt.id,
            version_number=1,
            content=content,
            change_summary=change_summary or "Initial version",
            created_by=context.email,
        )

        prompt_repository.create_prompt_details(**asdict(details_params))

    return prompt


def get_prompts(
    session: Session,
    context: UserContext,
    account_name: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    search: str | None = None,
    channels: list[str] | None = None,
    auto_commit: bool = True,
) -> list[db.Prompt]:
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    if resource_id:
        if resource_type == "project":
            project = project_service.get_project(session, resource_id)
            if not project or project.account_id != account.id:
                raise ValueError("Selected project is not available in the account")
        elif resource_type == "agent":
            agent = agent_service.get_agent(session, resource_id)
            if not agent or agent.account_id != account.id:
                raise ValueError("Selected agent is not available in the account")
        elif resource_type:
            raise ValueError(f"Unsupported resource type: {resource_type}")

    prompt_repository = PromptRepository(session, auto_commit=auto_commit)

    all_prompts = prompt_repository.get_prompts(
        resource_type, resource_id, search, channels
    )

    account_prompts = []
    for prompt in all_prompts:
        if prompt.resource_type == "project":
            project = project_service.get_project(session, prompt.resource_id)
            if project and project.account_id == account.id:
                account_prompts.append(prompt)
        elif prompt.resource_type == "agent":
            agent = agent_service.get_agent(session, prompt.resource_id)
            if agent and agent.account_id == account.id:
                account_prompts.append(prompt)

    return account_prompts


def update_prompt(
    session: Session,
    context: UserContext,
    account_name: str,
    prompt_id: uuid.UUID,
    name: str | None = None,
    default_prompt_id: str | None = None,
    channel: list[str] | None = None,
    content: str | None = None,
    change_summary: str | None = None,
    auto_commit: bool = True,
) -> db.Prompt:
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    prompt_repository = PromptRepository(session, auto_commit=auto_commit)

    existing_prompt = prompt_repository.get_prompt_by_id(prompt_id)
    if not existing_prompt:
        raise ValueError("Prompt not found")

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Prompt,
        author=context.email,
        account_id=account.id,
        auto_commit=auto_commit,
    ) as ctx:
        prompt_update_data = {}
        if name is not None:
            prompt_update_data["name"] = name
        if default_prompt_id is not None:
            prompt_update_data["default_prompt_id"] = default_prompt_id
        if channel is not None:
            prompt_update_data["channel"] = channel

        updated_prompt = existing_prompt
        if prompt_update_data:
            updated_prompt = prompt_repository.update_prompt(
                prompt_id, **prompt_update_data
            )
            if not updated_prompt:
                raise ValueError("Failed to update prompt")
            ctx.resource_id = str(updated_prompt.id)
            ctx.new_record = updated_prompt

        if content is not None:
            next_version = prompt_repository.get_next_version_number(prompt_id)

            details_params = PromptDetailsParams(
                prompt_id=prompt_id,
                version_number=next_version,
                content=content,
                change_summary=change_summary or f"Version {next_version}",
                created_by=context.email,
            )

            prompt_repository.create_prompt_details(**asdict(details_params))

        return updated_prompt


def get_prompt_versions(
    session: Session,
    context: UserContext,
    account_name: str,
    prompt_id: uuid.UUID,
    auto_commit: bool = True,
) -> list[db.PromptDetails]:
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    prompt_repository = PromptRepository(session, auto_commit=auto_commit)

    existing_prompt = prompt_repository.get_prompt_by_id(prompt_id)
    if not existing_prompt:
        raise ValueError("Prompt not found")

    if existing_prompt.resource_type == "project":
        project = project_service.get_project(session, existing_prompt.resource_id)
        if not project or project.account_id != account.id:
            raise ValueError("Prompt is not accessible in this account")
    elif existing_prompt.resource_type == "agent":
        agent = agent_service.get_agent(session, existing_prompt.resource_id)
        if not agent or agent.account_id != account.id:
            raise ValueError("Prompt is not accessible in this account")

    return prompt_repository.get_all_prompt_versions(prompt_id)


def delete_prompt(
    session: Session,
    context: UserContext,
    account_name: str,
    prompt_id: uuid.UUID,
    auto_commit: bool = True,
) -> None:
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")

    prompt_repository = PromptRepository(session, auto_commit=auto_commit)

    existing_prompt = prompt_repository.get_prompt_by_id(prompt_id)
    if not existing_prompt:
        raise ValueError("Prompt not found")

    if existing_prompt.resource_type == "project":
        project = project_service.get_project(session, existing_prompt.resource_id)
        if not project or project.account_id != account.id:
            raise ValueError("Prompt is not accessible in this account")
    elif existing_prompt.resource_type == "agent":
        agent = agent_service.get_agent(session, existing_prompt.resource_id)
        if not agent or agent.account_id != account.id:
            raise ValueError("Prompt is not accessible in this account")

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Prompt,
        author=context.email,
        account_id=account.id,
        auto_commit=auto_commit,
    ) as ctx:
        deleted = prompt_repository.delete_prompt(prompt_id)
        if not deleted:
            raise ValueError("Failed to delete prompt")

        ctx.resource_id = str(prompt_id)
        ctx.new_record = None
