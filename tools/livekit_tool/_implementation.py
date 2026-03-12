import json
import os

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool
from livekit import api as livekit_api

from agent.tool import ToolMetadata
from utils.log import logger


class LiveKitTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        room_name: str | None = None,
        transfer_destinations: dict[str, str] | None = None,
        destination_number: str | None = None,
        **kwargs,  # Accept and ignore unknown args from raw_config
    ):
        super().__init__(name="livekit_tool")
        self.tool_metadata = tool_metadata
        self.room_name = room_name
        self.lk_api = None
        lk_url = os.environ.get("LIVEKIT_URL", "")
        lk_key = os.environ.get("LIVEKIT_API_KEY", "")
        lk_secret = os.environ.get("LIVEKIT_API_SECRET", "")
        if lk_url and lk_key and lk_secret:
            self.lk_api = livekit_api.LiveKitAPI(
                url=lk_url, api_key=lk_key, api_secret=lk_secret
            )

        # Support flat destination_number as a shorthand for transfer_destinations
        if transfer_destinations is not None:
            self.transfer_destinations = transfer_destinations
        elif destination_number:
            self.transfer_destinations = {"general": destination_number}
        else:
            self.transfer_destinations = {}
        self.register(self.call_transfer)

    def _get_destination_for_purpose(self, purpose: str) -> str | None:
        """
        Look up destination number for given purpose.

        Args:
            purpose: The transfer purpose (e.g., "faq", "complaint", "general")

        Returns:
            The destination phone number/SIP URI, or None if not found.
            Falls back to "general" if specific purpose not found.
        """
        destination = self.transfer_destinations.get(purpose)

        if destination:
            logger.debug(
                f"[LiveKitTool._get_destination_for_purpose] Found destination for purpose '{purpose}'",
                extra={"purpose": purpose},
            )
            return destination

        # Fallback to "general"
        fallback = self.transfer_destinations.get("general")
        if fallback:
            logger.debug(
                f"[LiveKitTool._get_destination_for_purpose] Purpose '{purpose}' not found, "
                f"falling back to 'general'",
                extra={"purpose": purpose},
            )
            return fallback

        logger.warning(
            f"[LiveKitTool._get_destination_for_purpose] No destination found for purpose '{purpose}' "
            f"and no 'general' fallback configured",
            extra={
                "purpose": purpose,
                "available_purposes": list(self.transfer_destinations.keys()),
            },
        )
        return None

    @tool
    async def call_transfer(self, purpose: str = "general") -> str:
        """
        Transfer the current call to the appropriate department based on purpose.

        Use when customer needs human assistance. The purpose determines which
        department/number receives the transferred call.

        This tool updates the LiveKit agent metadata to trigger a call transfer.

        Args:
            purpose: The reason for transfer. Common values:
                - "general": Default transfer destination
                - "faq": Questions about menu, hours, location, etc.
                - "complaint": Customer complaints or escalations
                - "order_support": Issues with existing orders
                - "catering": Catering inquiries

        NEVER invoke this tool if user is NOT communicating via voice channel.

        Returns:
            str: Success or error message about the call transfer attempt.
        """
        log_extra = {
            "project_id": str(self.tool_metadata.project_id),
            "account_name": self.tool_metadata.account_name,
        }

        # Validate channel — defense in depth
        if (
            hasattr(self.tool_metadata, "channel")
            and self.tool_metadata.channel
            and self.tool_metadata.channel != "voice"
        ):
            error_msg = "Call transfer is only available for voice calls. This conversation is not a voice call."
            logger.warning(
                f"[LiveKitTool.call_transfer] {error_msg}",
                extra={**log_extra, "channel": self.tool_metadata.channel},
            )
            return error_msg

        # Validate LiveKit context is available
        if not self.lk_api:
            error_msg = (
                "LiveKit API client is not available. Call transfer is not possible."
            )
            logger.error(
                f"[LiveKitTool.call_transfer] {error_msg}",
                extra=log_extra,
            )
            return error_msg

        if not self.room_name:
            error_msg = (
                "LiveKit room info is not available. Call transfer is not possible."
            )
            logger.error(
                f"[LiveKitTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                },
            )
            return error_msg

        # Look up destination for the given purpose
        purpose = (purpose or "general").strip().lower() or "general"
        destination = self._get_destination_for_purpose(purpose)
        if not destination:
            error_msg = f"No transfer destination configured for purpose '{purpose}'."
            logger.error(
                f"[LiveKitTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "purpose": purpose,
                    "available_purposes": list(self.transfer_destinations.keys()),
                },
            )
            return error_msg

        try:
            # Update room metadata to trigger transfer
            # The LiveKit agent will listen to this metadata update event
            metadata_dict = {
                "transfer_purpose": purpose,
                "transfer_to": destination,
            }
            metadata = json.dumps(metadata_dict)

            logger.debug(
                f"[LiveKitTool.call_transfer] Updating room metadata "
                f"in room '{self.room_name}' to transfer to {destination}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "purpose": purpose,
                    "destination": destination,
                    "metadata": metadata,
                },
            )

            await self.lk_api.room.update_room_metadata(
                livekit_api.UpdateRoomMetadataRequest(
                    room=self.room_name,
                    metadata=metadata,
                )
            )

            logger.info(
                "[LiveKitTool.call_transfer] Successfully updated room metadata for call transfer",
                extra={
                    **log_extra,
                    "user_id": str(self.tool_metadata.user_id),
                    "session_id": str(self.tool_metadata.session_id),
                    "room_name": self.room_name,
                    "purpose": purpose,
                    "destination": destination,
                },
            )
            return "Call transfer has been initiated"

        except livekit_api.TwirpError as e:
            # Handle "room not found" / call already ended
            if e.code == livekit_api.TwirpErrorCode.NOT_FOUND:
                logger.info(
                    "[LiveKitTool.call_transfer] Room not found — call has likely ended",
                    extra={
                        **log_extra,
                        "room_name": self.room_name,
                        "twirp_code": e.code,
                    },
                )
                return "Call has already ended. Transfer is no longer possible."

            # Log with internal details for debugging
            logger.error(
                f"[LiveKitTool.call_transfer] LiveKit API error while updating metadata: {e.message}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "twirp_code": e.code,
                    "twirp_status": e.status,
                },
                exc_info=True,
            )
            # Return generic message to caller (don't leak backend details)
            return "Failed to update LiveKit metadata. Please try again."

        except Exception as e:
            # Log with internal details for debugging
            logger.error(
                f"[LiveKitTool.call_transfer] Unexpected error occurred while transferring call: {e}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "purpose": purpose,
                },
                exc_info=True,
            )
            # Return generic message to caller (don't leak backend details)
            return "An unexpected error occurred. Please try again."
