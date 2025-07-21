from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._builder import build_prompt
from api.routes.admin._utils import UserContext
from api.schemas.admin.prompt import CreatePromptRequest, Prompt
from services import prompt_service
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
