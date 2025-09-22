"""Voice service implementation."""

import asyncio
import os
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.admin._builder import build_voice_config
from api.schemas.admin.onboarding import (
    CreateVAPIAssistantRequest,
    DeleteVAPIAssistantResponse,
    VAPIAssistantResponse,
)
from api.schemas.admin.voice_config import (
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
)
from db.repositories.voice_config_repository import VoiceConfigRepositoryAsync
from services.voice_service.providers.vapi._implementation import VAPIProvider
from utils.log import logger


class VoiceService:
    """Service for handling voice-related operations with multiple provider support."""

    def __init__(self):
        self.vapi_provider = VAPIProvider()
        self._vapi_client = None

    def _get_vapi_client(self):
        """Get or create VAPI client instance."""
        if self._vapi_client is None:
            try:
                from vapi import Vapi

                api_key = os.environ.get("VAPI_API_KEY")
                if not api_key:
                    raise ValueError("VAPI_API_KEY environment variable is required")
                self._vapi_client = Vapi(token=api_key)
            except ImportError:
                raise ImportError(
                    "vapi-server-sdk is required for VAPI assistant management"
                )
        return self._vapi_client

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

    # VAPI Assistant Management Methods

    async def create_vapi_assistant(
        self, create_request: CreateVAPIAssistantRequest
    ) -> VAPIAssistantResponse:
        """Create a new VAPI assistant using the server SDK."""
        try:
            vapi_client = self._get_vapi_client()

            # Prepare assistant data with fixed defaults and configurable fields
            assistant_data = {
                "name": create_request.name,
                # Fixed transcriber configuration
                "transcriber": {
                    "provider": "deepgram",
                    "language": "en-US",
                },
                # Fixed model configuration with configurable system prompt
                "model": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "temperature": 0.7,
                    "messages": [
                        {
                            "role": "system",
                            "content": create_request.systemPrompt,
                        }
                    ],
                },
                # Voice configuration with configurable voiceId
                "voice": {
                    "provider": "cartesia",
                    "voiceId": create_request.voiceId,
                },
            }

            # Add optional configurable fields
            if create_request.firstMessage is not None:
                assistant_data["firstMessage"] = create_request.firstMessage
            if create_request.maxDurationSeconds is not None:
                assistant_data["maxDurationSeconds"] = create_request.maxDurationSeconds

            # Create assistant via VAPI API
            assistant = await asyncio.to_thread(
                vapi_client.assistants.create, **assistant_data
            )

            logger.info(f"Successfully created VAPI assistant: {assistant.id}")

            # Convert to response format
            return VAPIAssistantResponse(
                id=assistant.id,
                name=assistant.name or "",
                firstMessage=getattr(assistant, "firstMessage", None),
                maxDurationSeconds=getattr(assistant, "maxDurationSeconds", None),
                createdAt=getattr(
                    assistant, "created_at", getattr(assistant, "createdAt", "")
                ),
                updatedAt=getattr(
                    assistant, "updated_at", getattr(assistant, "updatedAt", "")
                ),
            )

        except Exception as e:
            logger.error(f"Failed to create VAPI assistant: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create VAPI assistant: {str(e)}",
                headers={"Content-Type": "application/json"},
            )

    async def get_vapi_assistant(self, assistant_id: str) -> VAPIAssistantResponse:
        """Get a VAPI assistant by ID."""
        try:
            vapi_client = self._get_vapi_client()
            assistant = await asyncio.to_thread(
                vapi_client.assistants.get, assistant_id
            )

            if not assistant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="VAPI assistant not found",
                )

            return VAPIAssistantResponse(
                id=assistant.id,
                name=assistant.name or "",
                firstMessage=getattr(assistant, "firstMessage", None),
                maxDurationSeconds=getattr(assistant, "maxDurationSeconds", None),
                createdAt=getattr(
                    assistant, "created_at", getattr(assistant, "createdAt", "")
                ),
                updatedAt=getattr(
                    assistant, "updated_at", getattr(assistant, "updatedAt", "")
                ),
            )

        except Exception as e:
            logger.error(f"Failed to get VAPI assistant {assistant_id}: {str(e)}")
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="VAPI assistant not found",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get VAPI assistant: {str(e)}",
                headers={"Content-Type": "application/json"},
            )

    async def delete_vapi_assistant(
        self, assistant_id: str
    ) -> DeleteVAPIAssistantResponse:
        """Delete a VAPI assistant."""
        try:
            vapi_client = self._get_vapi_client()
            await asyncio.to_thread(vapi_client.assistants.delete, assistant_id)

            logger.info(f"Successfully deleted VAPI assistant: {assistant_id}")

            return DeleteVAPIAssistantResponse(
                message="VAPI assistant deleted successfully",
                deleted_id=assistant_id,
            )

        except Exception as e:
            logger.error(f"Failed to delete VAPI assistant {assistant_id}: {str(e)}")
            if "not found" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="VAPI assistant not found",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete VAPI assistant: {str(e)}",
                headers={"Content-Type": "application/json"},
            )
