import logging
import uuid
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.admin.voice_config import (
    BatchUpdateVoiceConfigsRequest,
    BatchUpdateVoiceConfigsResponse,
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
    VoiceConfigUpdateResult,
)
from services import account_service, project_service
from services.auth_service import check_permission
from services.auth_types import UserRole
from services.voice_service import VoiceService

from ._utils import UserContext, not_found_error

logger = logging.getLogger(__name__)


def _check_project_access(
    context: UserContext,
    project,
    permission: str = "project.read",
) -> None:
    """Check if user has access to the project using RBAC."""
    # Admin has full access
    if context.role == UserRole.Admin:
        return
    # Check permission on project (needs sync session)
    import db

    sync_session = next(db.get_db())
    try:
        user_id = UUID(context.username)
        if not check_permission(
            user_id, f"projects/{project.id}", permission, sync_session
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
                headers={"Content-Type": "application/json"},
            )
    finally:
        sync_session.close()


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
    _check_project_access(context, project, "project.write")

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
    _check_project_access(context, project, "project.read")

    return voice_config


async def list_voice_configs_by_project(
    project_id: uuid.UUID,
    context: UserContext,
    async_session: AsyncSession,
) -> ListVoiceConfigsResponse:
    """
    List all voice configs for a project.
    Authorization is handled by require_project_permission in route decorator.
    """
    # Verify project exists
    project = await project_service.get_project_by_id_async(async_session, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

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
    _check_project_access(context, project, "project.write")

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
    _check_project_access(context, project, "project.write")

    return await voice_service.delete_voice_config(voice_config_id, async_session)


async def batch_update_voice_configs(
    request: BatchUpdateVoiceConfigsRequest,
    context: UserContext,
    async_session: AsyncSession,
) -> BatchUpdateVoiceConfigsResponse:
    """
    Update voice configs for multiple projects in batch.
    """
    # Verify account exists
    account = await account_service.get_account_async(
        async_session, request.account_name
    )
    if not account:
        raise not_found_error(f"Account '{request.account_name}' not found.")

    try:
        # Verify all projects belong to the account and collect project names
        project_names: dict[uuid.UUID, str] = {}
        results: list[VoiceConfigUpdateResult] = []
        total_failed = 0

        for voice_config_update in request.voice_config_updates:
            try:
                # Get project to verify ownership and get name
                project = await project_service.get_project_by_id_async(
                    async_session, voice_config_update.project_id
                )
                if not project:
                    results.append(
                        VoiceConfigUpdateResult(
                            project_id=voice_config_update.project_id,
                            project_name="Unknown",
                            success=False,
                            error_message="Project not found",
                        )
                    )
                    total_failed += 1
                    continue

                # Store project name eagerly before any async operations that might fail
                project_name = project.name

                # Verify project belongs to the account
                await async_session.refresh(project, ["account"])
                if project.account.name != request.account_name:
                    results.append(
                        VoiceConfigUpdateResult(
                            project_id=voice_config_update.project_id,
                            project_name=project_name,
                            success=False,
                            error_message="Project does not belong to specified account",
                        )
                    )
                    total_failed += 1
                    continue

                # Store project name for service layer
                project_names[voice_config_update.project_id] = project_name

            except Exception as e:
                logger.error(
                    f"Failed to verify project {voice_config_update.project_id}: {e}",
                    exc_info=True,
                )
                results.append(
                    VoiceConfigUpdateResult(
                        project_id=voice_config_update.project_id,
                        project_name="Unknown",
                        success=False,
                        error_message=str(e),
                    )
                )
                total_failed += 1

        # Filter out failed validation results to only process valid projects
        valid_updates = [
            update
            for update in request.voice_config_updates
            if update.project_id in project_names
        ]

        # Call service layer to perform batch updates
        voice_service = VoiceService()
        service_results, total_updated, service_failed = (
            await voice_service.batch_update_voice_configs(
                valid_updates, project_names, async_session
            )
        )

        # Combine validation failures with service results
        results.extend(service_results)
        total_failed += service_failed

        return BatchUpdateVoiceConfigsResponse(
            account_name=request.account_name,
            total_requested=len(request.voice_config_updates),
            total_updated=total_updated,
            total_failed=total_failed,
            results=results,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Batch voice config update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during batch voice config update",
        )
