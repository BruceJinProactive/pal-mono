"""Voice service implementation."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.admin.voice_config import (
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
    VoiceConfigUpdateResult,
)
from db.repositories.voice_config_repository import VoiceConfigRepositoryAsync
from services.voice_service._builder import build_voice_config


class VoiceService:
    """Service for handling voice-related operations."""

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

        # Check for duplicate language in same project
        # Language is already normalized (lowercased, stripped) by Pydantic validator
        existing_configs = await voice_repo.get_voice_configs_by_project(
            create_request.project_id
        )

        if any(
            (vc.language or "").strip().lower() == create_request.language
            for vc in existing_configs
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Voice config for language '{create_request.language}' already exists for this project",
                headers={"Content-Type": "application/json"},
            )

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
                voice_model=create_request.voice_model,
                transcriber=create_request.transcriber,
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

        # Check for duplicate language if updating language
        # Language is already normalized (lowercased, stripped) by Pydantic validator
        if update_request.language is not None:
            # Fetch existing config to get project_id and current language
            existing_config = await voice_repo.get_voice_config_by_id(voice_config_id)
            if not existing_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Voice config not found",
                )

            # Only check if actually changing the language
            normalized_existing = (existing_config.language or "").strip().lower()
            if update_request.language != normalized_existing:
                existing_configs = await voice_repo.get_voice_configs_by_project(
                    existing_config.project_id
                )

                if any(
                    (vc.language or "").strip().lower() == update_request.language
                    and vc.id != voice_config_id
                    for vc in existing_configs
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Voice config for language '{update_request.language}' already exists for this project",
                        headers={"Content-Type": "application/json"},
                    )

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
                    # Fetch existing config to get voice_id
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

    async def batch_update_voice_configs(
        self,
        voice_config_updates: list,
        project_names: dict[uuid.UUID, str],
        async_session: AsyncSession,
    ) -> tuple[list[VoiceConfigUpdateResult], int, int]:
        """
        Update multiple voice configs in batch.

        Args:
            voice_config_updates: List of VoiceConfigUpdateData objects
            project_names: Dict mapping project_id to project_name for result reporting
            async_session: Database session

        Returns:
            Tuple of (results list, total_updated count, total_failed count)
        """
        results: list[VoiceConfigUpdateResult] = []
        total_updated = 0
        total_failed = 0

        for voice_config_update in voice_config_updates:
            project_name = project_names.get(voice_config_update.project_id, "Unknown")
            try:
                # Get existing voice configs for this project
                voice_configs_response = await self.list_voice_configs_by_project(
                    voice_config_update.project_id, async_session
                )

                if not voice_configs_response.voice_configs:
                    results.append(
                        VoiceConfigUpdateResult(
                            project_id=voice_config_update.project_id,
                            project_name=project_name,
                            success=False,
                            error_message="No voice config found for project",
                        )
                    )
                    total_failed += 1
                    continue

                # Update the first voice config
                first_voice_config = voice_configs_response.voice_configs[0]

                # Create UpdateVoiceConfigRequest from the batch update data.
                # Use exclude_unset/exclude_none so we don't overwrite fields with null
                # when they were not provided in the batch payload.
                update_data = voice_config_update.model_dump(
                    exclude={"project_id"},
                    exclude_unset=True,
                    exclude_none=True,
                )
                update_request = UpdateVoiceConfigRequest(**update_data)

                updated_config = await self.update_voice_config(
                    first_voice_config.id, update_request, async_session
                )

                results.append(
                    VoiceConfigUpdateResult(
                        project_id=voice_config_update.project_id,
                        project_name=project_name,
                        success=True,
                        voice_config_id=updated_config.id,
                    )
                )
                total_updated += 1

            except Exception as e:
                results.append(
                    VoiceConfigUpdateResult(
                        project_id=voice_config_update.project_id,
                        project_name=project_name,
                        success=False,
                        error_message=str(e),
                    )
                )
                total_failed += 1

        return results, total_updated, total_failed
