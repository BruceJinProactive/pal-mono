"""Voice service implementation."""

import asyncio
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from api.routes.admin._builder import build_voice_config
from api.schemas.admin.voice_config import (
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
)
from db.repositories.voice_config_repository import VoiceConfigRepositoryAsync
from db.tables import VoiceConfig as VoiceConfigModel
from db.tables.change_log import ChangeResourceType
from services.history_service import change_log_context
from services.voice_service.providers.vapi._implementation import VAPIProvider
from utils.log import logger


def _create_voice_config_data_snapshot(voice_config):
    """Create a primitive data snapshot of voice config for cross-thread logging."""
    if voice_config is None:
        return None

    return {
        "id": voice_config.id,
        "project_id": voice_config.project_id,
        "language": voice_config.language,
        "voice_id": voice_config.voice_id,
        "replacements": voice_config.replacements,
        "first_message": voice_config.first_message,
        "transfer_message": voice_config.transfer_message,
        "speech_rate": voice_config.speech_rate,
        "background_sound": voice_config.background_sound,
        "raw_config": voice_config.raw_config,
        "created_at": voice_config.created_at,
        "updated_at": voice_config.updated_at,
    }


def _create_mock_voice_config_from_data(voice_config_data):
    """Build a transient instance of the real VoiceConfig model for diffing."""
    obj = VoiceConfigModel()
    for key, value in (voice_config_data or {}).items():
        setattr(obj, key, value)
    return obj


def _log_voice_config_change_sync(
    sync_engine,
    author: str,
    account_id: uuid.UUID,
    project_id: uuid.UUID,
    operation_type: str,  # 'create', 'update', or 'delete'
    old_voice_config_data=None,
    new_voice_config_data=None,
) -> None:
    """Helper function to run sync voice config change logging by re-querying ORM instances."""
    sync_session_factory = sessionmaker(bind=sync_engine)

    try:
        with sync_session_factory() as sync_session:
            if operation_type == "create":
                new_voice_config = _create_mock_voice_config_from_data(
                    new_voice_config_data
                )
                old_voice_config = None

                with change_log_context(
                    session=sync_session,
                    resource_type=ChangeResourceType.Project,
                    author=author,
                    account_id=account_id,
                    resource_id=str(project_id),
                    old_record=old_voice_config,
                    new_record=new_voice_config,
                    auto_commit=True,
                ):
                    pass

            elif operation_type == "update":
                old_voice_config = _create_mock_voice_config_from_data(
                    old_voice_config_data
                )
                new_voice_config = _create_mock_voice_config_from_data(
                    new_voice_config_data
                )

                with change_log_context(
                    session=sync_session,
                    resource_type=ChangeResourceType.Project,
                    author=author,
                    account_id=account_id,
                    resource_id=str(project_id),
                    old_record=old_voice_config,
                    new_record=new_voice_config,
                    auto_commit=True,
                ):
                    pass

            elif operation_type == "delete":
                old_voice_config = _create_mock_voice_config_from_data(
                    old_voice_config_data
                )
                new_voice_config = None

                with change_log_context(
                    session=sync_session,
                    resource_type=ChangeResourceType.Project,
                    author=author,
                    account_id=account_id,
                    resource_id=str(project_id),
                    old_record=old_voice_config,
                    new_record=new_voice_config,
                    auto_commit=True,
                ):
                    pass

            else:
                logger.warning(f"Unknown operation type: {operation_type}")

    except Exception as e:
        logger.error(f"Failed to log voice config {operation_type}: {e}", exc_info=True)


class VoiceService:
    """Service for handling voice-related operations with multiple provider support."""

    def __init__(self):
        self.vapi_provider = VAPIProvider()

    async def create_vapi_assistant_response(
        self,
        caller_info: dict,
        project_id: uuid.UUID,
        session: AsyncSession,
    ) -> dict:
        """
        Create VAPI assistant response configuration.

        Args:
            caller_info: Dictionary containing caller information with keys:
                - sender_identifier: customer phone number
                - recipient_identifier: business phone number
                - call_id: unique call identifier
            project_id: The project identifier
            session: The database session

        Returns:
            dict: Assistant response configuration for VAPI
        """
        return await self.vapi_provider.get_assistant_response(
            caller_info, project_id, session
        )

    async def create_voice_config(
        self,
        create_request: CreateVoiceConfigRequest,
        async_session: AsyncSession,
        author: str,
        account_id: uuid.UUID,
    ) -> VoiceConfig:
        """Create a new voice config with business logic validation."""

        # Create voice config using repository
        voice_repo = VoiceConfigRepositoryAsync(async_session, auto_commit=True)
        try:
            db_voice_config = await voice_repo.create_voice_config(
                project_id=create_request.project_id,
                language=create_request.language,
                voice_id=create_request.voice_id,
                first_message=create_request.first_message,
                transfer_message=create_request.transfer_message,
                replacements=create_request.replacements or {},
                speech_rate=(
                    create_request.speech_rate.value
                    if create_request.speech_rate
                    else None
                ),
                background_sound=create_request.background_sound,
                raw_config=create_request.raw_config or {},
            )

            # Capture voice config data for change logging
            voice_config_data_snapshot = _create_voice_config_data_snapshot(
                db_voice_config
            )

            # Schedule background logging (non-blocking) with captured voice config data
            asyncio.get_event_loop().run_in_executor(
                None,
                _log_voice_config_change_sync,
                async_session.bind.sync_engine,
                author,
                account_id,
                create_request.project_id,
                "create",  # operation type
                None,  # old_voice_config_data
                voice_config_data_snapshot,  # new_voice_config_data
            )

            return build_voice_config(db_voice_config)
        except Exception as e:
            await async_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create voice config: {str(e)}",
                headers={"Content-Type": "application/json"},
            )

    async def get_voice_config(
        self,
        voice_config_id: uuid.UUID,
        async_session: AsyncSession,
    ) -> VoiceConfig:
        """Get voice config by ID."""
        voice_repo = VoiceConfigRepositoryAsync(async_session)

        # Get voice config by ID
        db_voice_config = await voice_repo.get_voice_config_by_id(voice_config_id)
        if not db_voice_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Voice config not found",
            )

        return build_voice_config(db_voice_config)

    async def list_voice_configs_by_project(
        self,
        project_id: uuid.UUID,
        async_session: AsyncSession,
    ) -> ListVoiceConfigsResponse:
        """List all voice configs for a project."""
        voice_repo = VoiceConfigRepositoryAsync(async_session)
        voice_configs = await voice_repo.get_voice_configs_by_project(project_id)

        return ListVoiceConfigsResponse(
            voice_configs=[build_voice_config(vc) for vc in voice_configs],
            total_count=len(voice_configs),
        )

    async def update_voice_config(
        self,
        voice_config_id: uuid.UUID,
        update_request: UpdateVoiceConfigRequest,
        async_session: AsyncSession,
        author: str,
        account_id: uuid.UUID,
    ) -> VoiceConfig:
        """Update an existing voice config."""
        voice_repo = VoiceConfigRepositoryAsync(async_session, auto_commit=True)

        # Get the existing voice config for change logging
        existing_voice_config = await voice_repo.get_voice_config_by_id(voice_config_id)
        if not existing_voice_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Voice config not found",
            )

        # Capture old state for change logging
        old_voice_config_data = _create_voice_config_data_snapshot(
            existing_voice_config
        )

        # Build update kwargs - exclude fields that weren't set
        update_kwargs = update_request.model_dump(exclude_unset=True)
        if "speech_rate" in update_kwargs and update_kwargs["speech_rate"] is not None:
            update_kwargs["speech_rate"] = update_kwargs["speech_rate"].value

        try:
            updated_voice_config = await voice_repo.update_voice_config(
                voice_config_id=voice_config_id, **update_kwargs
            )

            if not updated_voice_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Voice config not found",
                )

            # Capture new state for change logging
            new_voice_config_data = _create_voice_config_data_snapshot(
                updated_voice_config
            )

            # Schedule background logging (non-blocking) with captured voice config data
            asyncio.get_event_loop().run_in_executor(
                None,
                _log_voice_config_change_sync,
                async_session.bind.sync_engine,
                author,
                account_id,
                updated_voice_config.project_id,
                "update",  # operation type
                old_voice_config_data,  # old_voice_config_data
                new_voice_config_data,  # new_voice_config_data
            )

            return build_voice_config(updated_voice_config)
        except Exception as e:
            await async_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update voice config: {str(e)}",
                headers={"Content-Type": "application/json"},
            )

    async def delete_voice_config(
        self,
        voice_config_id: uuid.UUID,
        async_session: AsyncSession,
        author: str,
        account_id: uuid.UUID,
    ):
        """Delete a voice config."""
        voice_repo = VoiceConfigRepositoryAsync(async_session, auto_commit=True)

        # Get the existing voice config for change logging
        existing_voice_config = await voice_repo.get_voice_config_by_id(voice_config_id)
        if not existing_voice_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Voice config not found",
            )

        # Capture old state for change logging
        old_voice_config_data = _create_voice_config_data_snapshot(
            existing_voice_config
        )
        project_id = existing_voice_config.project_id

        try:
            deleted = await voice_repo.delete_voice_config(voice_config_id)

            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Voice config not found",
                )

            # Schedule background logging (non-blocking) with captured voice config data
            asyncio.get_event_loop().run_in_executor(
                None,
                _log_voice_config_change_sync,
                async_session.bind.sync_engine,
                author,
                account_id,
                project_id,
                "delete",  # operation type
                old_voice_config_data,  # old_voice_config_data
                None,  # new_voice_config_data
            )

            return {"message": "succeed"}
        except Exception as e:
            await async_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete voice config: {str(e)}",
                headers={"Content-Type": "application/json"},
            )
