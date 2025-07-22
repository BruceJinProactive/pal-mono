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
    UpdatePromptRequest,
)
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
