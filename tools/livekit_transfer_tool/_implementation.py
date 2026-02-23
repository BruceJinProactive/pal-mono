from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool
from livekit import api as livekit_api

from agent.tool import ToolMetadata
from utils.log import logger


def _mask_phone(phone: str | None) -> str:
    """Mask phone number for logging, showing only last 4 digits."""
    if not phone:
        return "None"
    if len(phone) <= 4:
        return "****"
    return f"***{phone[-4:]}"


class LiveKitTransferTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        transfer_destinations: dict[str, str],
        transfer_message: str | None = None,
        show_agent_caller_id: bool = False,
        lk_api: livekit_api.LiveKitAPI | None = None,
        room_name: str | None = None,
        participant_identity: str | None = None,
        **kwargs,  # Accept and ignore unknown args from raw_config
    ):
        super().__init__(name="livekit_transfer_tool")
        self.tool_metadata = tool_metadata
        self.transfer_destinations = transfer_destinations
        self.transfer_message = (
            transfer_message
            or "I'll transfer you to our team. Just hang tight for a moment."
        )
        self.show_agent_caller_id = show_agent_caller_id
        self.lk_api = lk_api
        self.room_name = room_name
        self.participant_identity = participant_identity
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
                f"[LiveKitTransferTool._get_destination_for_purpose] Found destination for purpose '{purpose}': "
                f"{_mask_phone(destination)}"
            )
            return destination

        # Fallback to "general"
        fallback = self.transfer_destinations.get("general")
        if fallback:
            logger.debug(
                f"[LiveKitTransferTool._get_destination_for_purpose] Purpose '{purpose}' not found, "
                f"falling back to 'general': {_mask_phone(fallback)}"
            )
            return fallback

        logger.warning(
            f"[LiveKitTransferTool._get_destination_for_purpose] No destination found for purpose '{purpose}' "
            f"and no 'general' fallback configured",
            extra={
                "purpose": purpose,
                "available_purposes": list(self.transfer_destinations.keys()),
            },
        )
        return None

    def _build_transfer_to(self, destination: str) -> str:
        """
        Build the transfer_to URI for the LiveKit SIP REFER request.

        LiveKit transfer_sip_participant expects a SIP URI or tel: URI.
        Phone numbers are formatted as tel:+1XXXXXXXXXX.
        SIP URIs are passed through as-is.

        Args:
            destination: Phone number (E.164) or SIP URI from contacts table.

        Returns:
            Formatted transfer_to string for the LiveKit API.
        """
        if destination.lower().startswith("sip:"):
            return destination

        # Phone number — wrap in tel: URI
        return f"tel:{destination}"

    @tool
    async def call_transfer(self, purpose: str = "general") -> str:
        """
        Transfer the current call to the appropriate department based on purpose.

        Use when customer needs human assistance. The purpose determines which
        department/number receives the transferred call.

        Supports phone numbers ("+1234567890") or SIP URIs ("sip:+1234567890@sip.provider.com").

        Args:
            purpose: The reason for transfer. Common values:
                - "general": Default transfer destination
                - "faq": Questions about menu, hours, location, etc.
                - "complaint": Customer complaints or escalations
                - "order_support": Issues with existing orders
                - "catering": Catering inquiries
                Defaults to "general" if specified purpose is not configured.

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
                f"[LiveKitTransferTool.call_transfer] {error_msg}",
                extra={**log_extra, "channel": self.tool_metadata.channel},
            )
            return error_msg

        # Look up destination for the given purpose
        destination = self._get_destination_for_purpose(purpose)
        if not destination:
            error_msg = f"No transfer destination configured for purpose '{purpose}'."
            logger.error(
                f"[LiveKitTransferTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "purpose": purpose,
                    "available_purposes": list(self.transfer_destinations.keys()),
                },
            )
            return error_msg

        # Validate LiveKit context is available
        if not self.lk_api:
            error_msg = (
                "LiveKit API client is not available. Call transfer is not possible."
            )
            logger.error(
                f"[LiveKitTransferTool.call_transfer] {error_msg}",
                extra=log_extra,
            )
            return error_msg

        if not self.room_name or not self.participant_identity:
            error_msg = "LiveKit room or participant info is not available. Call transfer is not possible."
            logger.error(
                f"[LiveKitTransferTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "participant_identity": self.participant_identity,
                },
            )
            return error_msg

        # Build the transfer_to URI
        transfer_to = self._build_transfer_to(destination)

        # Build transfer request with optional SIP headers for caller ID
        headers: dict[str, str] = {}
        if self.show_agent_caller_id:
            if self.tool_metadata.store_phone:
                headers["X-Caller-ID"] = self.tool_metadata.store_phone
                logger.debug(
                    f"[LiveKitTransferTool.call_transfer] Setting caller ID header to agent phone: "
                    f"{_mask_phone(self.tool_metadata.store_phone)}"
                )
        else:
            if self.tool_metadata.customer_phone:
                headers["X-Caller-ID"] = self.tool_metadata.customer_phone
                logger.debug(
                    f"[LiveKitTransferTool.call_transfer] Setting caller ID header to customer phone: "
                    f"{_mask_phone(self.tool_metadata.customer_phone)}"
                )

        try:
            logger.debug(
                f"[LiveKitTransferTool.call_transfer] Initiating SIP REFER transfer "
                f"in room '{self.room_name}' for participant '{self.participant_identity}' "
                f"to {_mask_phone(destination)}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "participant_identity": self.participant_identity,
                    "purpose": purpose,
                },
            )

            transfer_request = livekit_api.TransferSIPParticipantRequest(
                participant_identity=self.participant_identity,
                room_name=self.room_name,
                transfer_to=transfer_to,
                play_dialtone=True,
                headers=headers if headers else {},
            )

            await self.lk_api.sip.transfer_sip_participant(transfer_request)

            logger.info(
                "[LiveKitTransferTool.call_transfer] Successfully initiated call transfer",
                extra={
                    **log_extra,
                    "user_id": str(self.tool_metadata.user_id),
                    "session_id": str(self.tool_metadata.session_id),
                    "room_name": self.room_name,
                    "destination": _mask_phone(destination),
                    "purpose": purpose,
                },
            )
            return "Call has been transferred"

        except livekit_api.TwirpError as e:
            # Handle "participant not found" / call already ended
            if e.code == livekit_api.TwirpErrorCode.NOT_FOUND:
                logger.info(
                    "[LiveKitTransferTool.call_transfer] Participant not found — call has likely ended",
                    extra={
                        **log_extra,
                        "room_name": self.room_name,
                        "participant_identity": self.participant_identity,
                        "twirp_code": e.code,
                    },
                )
                return "Call has already ended. Transfer is no longer possible."

            error_msg = f"LiveKit API error while transferring call: {e.message}"
            logger.error(
                f"[LiveKitTransferTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "twirp_code": e.code,
                    "twirp_status": e.status,
                },
                exc_info=True,
            )
            return error_msg

        except Exception as e:
            error_msg = f"Unexpected error occurred while transferring call: {e}"
            logger.error(
                f"[LiveKitTransferTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "room_name": self.room_name,
                    "participant_identity": self.participant_identity,
                },
                exc_info=True,
            )
            return error_msg
