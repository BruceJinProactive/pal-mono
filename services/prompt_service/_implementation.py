from dataclasses import asdict

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from db.repositories.prompt_repository import PromptRepository
from db.tables.change_log import ChangeResourceType
from services import account_service, agent_service, project_service
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
