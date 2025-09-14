"""Voice service implementation."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.voice_service.providers.vapi._implementation import VAPIProvider


class VoiceService:
    """Service for handling voice-related operations with multiple provider support."""

    def __init__(self):
        self.vapi_provider = VAPIProvider()

    async def create_vapi_assistant_response(
        self,
        caller_info: dict,
        project_id: UUID,
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
