"""Voice service implementation."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.admin.voice_config import (
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
)
from db.repositories.voice_config_repository import VoiceConfigRepositoryAsync
from services.voice_service._builder import build_voice_config
from services.voice_service.providers.vapi._implementation import VAPIProvider


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
    ) -> VoiceConfig:
        """Create a new voice config with business logic validation."""

        # Determine cloned_voice_id based on the cloned flag
        cloned_voice_id = None
        if create_request.cloned:
            cloned_voice_id = create_request.voice_id

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
                cloned_voice_id=cloned_voice_id,
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
    ) -> VoiceConfig:
        """Update an existing voice config."""
        voice_repo = VoiceConfigRepositoryAsync(async_session, auto_commit=True)

        # Build update kwargs - exclude fields that weren't set
        update_kwargs = update_request.model_dump(exclude_unset=True)
        if "speech_rate" in update_kwargs and update_kwargs["speech_rate"] is not None:
            update_kwargs["speech_rate"] = update_kwargs["speech_rate"].value

        # Handle cloned voice ID logic
        if "cloned" in update_kwargs:
            cloned = update_kwargs.pop("cloned")  # Remove cloned from kwargs
            if cloned:
                # If cloned is True, set cloned_voice_id to the voice_id
                if "voice_id" in update_kwargs:
                    # Use the new voice_id being set
                    update_kwargs["cloned_voice_id"] = update_kwargs["voice_id"]
                else:
                    # Get the current voice_id from the database
                    existing_config = await voice_repo.get_voice_config_by_id(
                        voice_config_id
                    )
                    if existing_config:
                        update_kwargs["cloned_voice_id"] = existing_config.voice_id
            # If cloned is False, we don't update cloned_voice_id (keep existing value)

        try:
            updated_voice_config = await voice_repo.update_voice_config(
                voice_config_id=voice_config_id, **update_kwargs
            )

            if not updated_voice_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Voice config not found",
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
    ):
        """Delete a voice config."""
        voice_repo = VoiceConfigRepositoryAsync(async_session, auto_commit=True)

        try:
            deleted = await voice_repo.delete_voice_config(voice_config_id)

            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Voice config not found",
                )

            return {"message": "succeed"}
        except Exception as e:
            await async_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete voice config: {str(e)}",
                headers={"Content-Type": "application/json"},
            )
