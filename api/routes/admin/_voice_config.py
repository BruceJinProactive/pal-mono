import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.admin.voice_config import (
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
)
from services import project_service
from services.voice_service import VoiceService

from ._auth import authorize_user_account
from ._utils import UserContext


async def create_voice_config(
    create_request: CreateVoiceConfigRequest,
    context: UserContext,
    async_session: AsyncSession,
) -> VoiceConfig:
    """Create a new voice config."""
    # Verify project exists and user has access
    project = await project_service.get_project_by_id_async(
        async_session, create_request.project_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    await async_session.refresh(project, ["account"])
    authorize_user_account(context, project.account.name)

    voice_service = VoiceService()
    return await voice_service.create_voice_config(create_request, async_session)


async def get_voice_config(
    voice_config_id: uuid.UUID,
    context: UserContext,
    async_session: AsyncSession,
) -> VoiceConfig:
    """Get voice config by ID."""
    voice_service = VoiceService()
    voice_config = await voice_service.get_voice_config(voice_config_id, async_session)

    # Get project to authorize access
    project = await project_service.get_project_by_id_async(
        async_session, voice_config.project_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    await async_session.refresh(project, ["account"])
    authorize_user_account(context, project.account.name)

    return voice_config


async def list_voice_configs_by_project(
    project_id: uuid.UUID,
    context: UserContext,
    async_session: AsyncSession,
) -> ListVoiceConfigsResponse:
    """List all voice configs for a project."""
    # Verify project exists and user has access
    project = await project_service.get_project_by_id_async(async_session, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    await async_session.refresh(project, ["account"])
    authorize_user_account(context, project.account.name)

    voice_service = VoiceService()
    return await voice_service.list_voice_configs_by_project(project_id, async_session)


async def update_voice_config(
    voice_config_id: uuid.UUID,
    update_request: UpdateVoiceConfigRequest,
    context: UserContext,
    async_session: AsyncSession,
) -> VoiceConfig:
    """Update an existing voice config."""
    voice_service = VoiceService()

    # Get the voice config first to check project authorization
    existing_config = await voice_service.get_voice_config(
        voice_config_id, async_session
    )

    # Get project to authorize access
    project = await project_service.get_project_by_id_async(
        async_session, existing_config.project_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    await async_session.refresh(project, ["account"])
    authorize_user_account(context, project.account.name)

    return await voice_service.update_voice_config(
        voice_config_id, update_request, async_session
    )


async def delete_voice_config(
    voice_config_id: uuid.UUID,
    context: UserContext,
    async_session: AsyncSession,
):
    """Delete a voice config."""
    voice_service = VoiceService()

    # Get the voice config first to check project authorization
    existing_config = await voice_service.get_voice_config(
        voice_config_id, async_session
    )

    # Get project to authorize access
    project = await project_service.get_project_by_id_async(
        async_session, existing_config.project_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    await async_session.refresh(project, ["account"])
    authorize_user_account(context, project.account.name)

    return await voice_service.delete_voice_config(voice_config_id, async_session)
