import os

import httpx
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from db.repositories.conversation_repository import ConversationRepositoryAsync
from db.session import AsyncSessionLocal
from utils.log import logger


def _mask_phone(phone: str | None) -> str:
    """Mask phone number for logging, showing only last 4 digits."""
    if not phone:
        return "None"
    if len(phone) <= 4:
        return "****"
    return f"***{phone[-4:]}"


async def _get_control_url_from_vapi(call_id: str) -> str:
    """
    Fetch control URL from Vapi API using call ID.

    Args:
        call_id: The Vapi call ID

    Returns:
        str: The control URL for the call

    Raises:
        Exception: If unable to fetch control URL
    """
    vapi_api_key = os.environ.get("VAPI_API_KEY")
    if not vapi_api_key:
        logger.error(
            "[VapiTool._get_control_url_from_vapi] VAPI_API_KEY not configured"
        )
        raise Exception(
            "[VapiTool._get_control_url_from_vapi] VAPI_API_KEY not configured"
        )

    try:
        vapi_url = f"https://api.vapi.ai/call/{call_id}"
        headers = {"Authorization": f"Bearer {vapi_api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(vapi_url, headers=headers)
            response.raise_for_status()

            call_data = response.json()
        # Use `or {}` because .get() returns None if key exists with None value
        control_url = (call_data.get("monitor") or {}).get("controlUrl")

        if not control_url:
            logger.error(
                f"[VapiTool._get_control_url_from_vapi] No control URL found in Vapi call response for call id {call_id}"
            )
            raise Exception(
                f"[VapiTool._get_control_url_from_vapi] No control URL found in Vapi call response for call id {call_id}"
            )

        logger.debug(
            f"[VapiTool._get_control_url_from_vapi] Successfully retrieved control URL for call id {call_id}: {control_url}"
        )
        return control_url

    except httpx.RequestError as e:
        logger.error(
            f"[VapiTool._get_control_url_from_vapi] Network error occurred while fetching call data from Vapi for call id {call_id}: {e}",
            exc_info=True,
        )
        raise Exception(
            f"[VapiTool._get_control_url_from_vapi] Network error occurred while fetching call data from Vapi for call id {call_id}: {e}"
        )

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[VapiTool._get_control_url_from_vapi] HTTP error {e.response.status_code} occurred while fetching call data from Vapi for call id {call_id}: {e.response.text}",
            exc_info=True,
        )
        raise Exception(
            f"[VapiTool._get_control_url_from_vapi] HTTP error {e.response.status_code} occurred while fetching call data from Vapi for call id {call_id}: {e.response.text}"
        )
    except Exception as e:
        logger.error(
            f"[VapiTool._get_control_url_from_vapi] Unexpected error occurred while fetching call data from Vapi for call id {call_id}: {e}",
            exc_info=True,
        )
        raise Exception(
            f"[VapiTool._get_control_url_from_vapi] Unexpected error occurred while fetching call data from Vapi for call id {call_id}: {e}"
        )


class VapiTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        transfer_destinations: dict[str, str],
        transfer_message: str | None = None,
        show_agent_caller_id: bool = False,
    ):
        super().__init__(name="vapi_tool")
        self.tool_metadata = tool_metadata
        self.transfer_destinations = transfer_destinations
        self.transfer_message = (
            transfer_message
            or "I'll transfer you to our team. Just hang tight for a moment."
        )
        self.show_agent_caller_id = show_agent_caller_id
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
        purpose = "general"
        destination = self.transfer_destinations.get(purpose)

        if destination:
            logger.debug(
                f"[VapiTool._get_destination_for_purpose] Found destination for purpose '{purpose}': {destination}"
            )
            return destination

        # Fallback to "general"
        fallback = self.transfer_destinations.get("general")
        if fallback:
            logger.debug(
                f"[VapiTool._get_destination_for_purpose] Purpose '{purpose}' not found, "
                f"falling back to 'general': {fallback}"
            )
            return fallback

        logger.warning(
            f"[VapiTool._get_destination_for_purpose] No destination found for purpose '{purpose}' "
            f"and no 'general' fallback configured",
            extra={
                "purpose": purpose,
                "available_purposes": list(self.transfer_destinations.keys()),
            },
        )
        return None

    def _build_transfer_payload(self, destination_number: str) -> dict:
        """Build transfer payload for SIP URI or phone number.

        Args:
            destination_number: The phone number or SIP URI to transfer to.

        Returns:
            dict: The transfer payload for the Vapi API.

        Raises:
            ValueError: If destination_number is empty or None.
        """
        if not destination_number:
            raise ValueError("destination_number cannot be empty or None")
        is_sip = destination_number.lower().startswith("sip:")
        if is_sip:
            # Use <Dial> instead of <Refer> for PSTN compatibility.
            # <Refer> only works when caller is on SIP leg, but our customers
            # call from PSTN phones. <Dial> keeps Twilio in the call path
            # and bridges PSTN caller to SIP endpoint.
            # IMPORTANT: "mode" is required when using transferPlan per VAPI support
            # NOTE: Do NOT set callerId for SIP transfers - adding callerId to the
            # destination object causes VAPI to ignore transferPlan.sipVerb and fall
            # back to using <Refer>, which fails for PSTN callers. For SIP, caller ID
            # must be configured at the SIP trunk level, not per-transfer.
            destination = {
                "type": "sip",
                "sipUri": destination_number,
                "transferPlan": {
                    "mode": "blind-transfer",
                    "sipVerb": "dial",
                },
            }
            logger.debug(
                "[VapiTool._build_transfer_payload] SIP transfer - callerId not set "
                "(must be configured at trunk level to preserve sipVerb: dial)"
            )
        else:
            destination = {"type": "number", "number": destination_number}
            # Set caller ID for phone number transfers only
            # When show_agent_caller_id is True: store sees AI agent's phone number
            # When show_agent_caller_id is False (default): store sees customer's phone number
            if self.show_agent_caller_id:
                if self.tool_metadata and self.tool_metadata.store_phone:
                    destination["callerId"] = self.tool_metadata.store_phone
                    logger.debug(
                        f"[VapiTool._build_transfer_payload] Setting callerId to agent phone: "
                        f"{_mask_phone(self.tool_metadata.store_phone)}"
                    )
                else:
                    logger.warning(
                        "[VapiTool._build_transfer_payload] show_agent_caller_id is enabled but "
                        "store_phone is unavailable; callerId will not be set"
                    )
            else:
                if self.tool_metadata and self.tool_metadata.customer_phone:
                    destination["callerId"] = self.tool_metadata.customer_phone
                    logger.debug(
                        f"[VapiTool._build_transfer_payload] Setting callerId to customer phone: "
                        f"{_mask_phone(self.tool_metadata.customer_phone)}"
                    )
                else:
                    logger.debug(
                        "[VapiTool._build_transfer_payload] customer_phone is unavailable; "
                        "callerId will not be set"
                    )

        # Set caller ID based on project preference
        # When show_agent_caller_id is True: store sees AI agent's phone number
        # When show_agent_caller_id is False (default): store sees customer's phone number
        if self.show_agent_caller_id:
            if self.tool_metadata and self.tool_metadata.store_phone:
                destination["callerId"] = self.tool_metadata.store_phone
                logger.debug(
                    f"[VapiTool._build_transfer_payload] Setting callerId to agent phone: "
                    f"{_mask_phone(self.tool_metadata.store_phone)}"
                )
            else:
                logger.warning(
                    "[VapiTool._build_transfer_payload] show_agent_caller_id is enabled but "
                    "store_phone is unavailable; callerId will not be set"
                )
        else:
            if self.tool_metadata and self.tool_metadata.customer_phone:
                destination["callerId"] = self.tool_metadata.customer_phone
                logger.debug(
                    f"[VapiTool._build_transfer_payload] Setting callerId to customer phone: "
                    f"{_mask_phone(self.tool_metadata.customer_phone)}"
                )
            else:
                logger.debug(
                    "[VapiTool._build_transfer_payload] customer_phone is unavailable; "
                    "callerId will not be set"
                )

        logger.debug(
            f"[VapiTool._build_transfer_payload] Detected destination type: {'SIP' if is_sip else 'phone number'} for {destination_number}"
        )
        return {
            "type": "transfer",
            "destination": destination,
            "content": self.transfer_message,
        }

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
                Defaults to "general" if specified purpose is not configured.

        NEVER invoke this tool if user is NOT communicating via voice channel.

        Returns:
            str: Success or error message about the call transfer attempt.
        """
        # Validate channel - defense in depth
        if (
            hasattr(self.tool_metadata, "channel")
            and self.tool_metadata.channel
            and self.tool_metadata.channel != "voice"
        ):
            error_msg = "Call transfer is only available for voice calls. This conversation is not a voice call."
            logger.warning(
                f"[VapiTool.call_transfer] {error_msg}",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "channel": self.tool_metadata.channel,
                },
            )
            return error_msg

        # Look up destination for the given purpose
        destination_number = self._get_destination_for_purpose(purpose)
        if not destination_number:
            error_msg = f"No transfer destination configured for purpose '{purpose}'."
            logger.error(
                f"[VapiTool.call_transfer] {error_msg}",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "purpose": purpose,
                    "available_purposes": list(self.transfer_destinations.keys()),
                },
            )
            return error_msg

        # Get control URL from the conversations table using session_id (conversation_id)
        conversation_id = self.tool_metadata.session_id
        # get last message, and get ctrl url from the message metadata
        if not conversation_id:
            error_msg = "No conversation ID available. Call transfer is not possible."
            logger.error(
                f"[VapiTool.call_transfer] {error_msg}",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "user_id": str(self.tool_metadata.user_id),
                },
            )
            return error_msg
        logger.debug(
            f"[VapiTool.call_transfer] Initiating call transfer for conversation {conversation_id}"
        )
        async with AsyncSessionLocal() as db:
            # Get conversation and fetch control URL from Vapi API
            try:
                conversation_repo = ConversationRepositoryAsync(db)
                conversation = await conversation_repo.get_conversation_by_id(
                    conversation_id
                )

                if not conversation:
                    error_msg = f"Conversation {conversation_id} not found. Call transfer is not possible."
                    logger.error(
                        f"[VapiTool.call_transfer] {error_msg}",
                        extra={
                            "project_id": str(self.tool_metadata.project_id),
                            "account_name": self.tool_metadata.account_name,
                            "conversation_id": str(conversation_id),
                            "user_id": str(self.tool_metadata.user_id),
                        },
                    )
                    return error_msg

                # Get control URL from Vapi API if not stored in conversation
                control_url = conversation.vapi_control_url
                call_id = conversation.call_id
                if not control_url:
                    logger.debug(
                        f"[VapiTool.call_transfer] No control URL stored for conversation {conversation_id}. Fetching from Vapi API."
                    )
                    logger.debug(
                        f"[VapiTool.call_transfer] Call id for conversation {conversation_id}: {call_id}"
                    )

                    if not call_id:
                        error_msg = "No call ID available for this conversation. Call transfer is not possible."
                        logger.error(
                            f"[VapiTool.call_transfer] {error_msg}",
                            extra={
                                "project_id": str(self.tool_metadata.project_id),
                                "account_name": self.tool_metadata.account_name,
                                "conversation_id": str(conversation_id),
                                "user_id": str(self.tool_metadata.user_id),
                                "destination_number": destination_number,
                                "purpose": purpose,
                                "vapi_control_url_present": bool(
                                    conversation.vapi_control_url
                                ),
                                "conversation_status": (
                                    str(conversation.status)
                                    if conversation.status
                                    else None
                                ),
                            },
                        )
                        return error_msg

                    control_url = await _get_control_url_from_vapi(call_id)
                    logger.info(
                        "[VapiTool.call_transfer] Fetched control URL from VAPI API (fallback)",
                        extra={
                            "call_id": call_id,
                            "conversation_id": str(conversation_id),
                        },
                    )

                logger.debug(
                    f"[VapiTool.call_transfer] Retrieved control URL for conversation {conversation_id}: {control_url}"
                )

            except Exception as e:
                error_msg = f"Error fetching call data: {e}"
                logger.error(
                    f"[VapiTool.call_transfer] {error_msg}",
                    extra={
                        "project_id": str(self.tool_metadata.project_id),
                        "account_name": self.tool_metadata.account_name,
                        "conversation_id": str(conversation_id),
                        "user_id": str(self.tool_metadata.user_id),
                    },
                    exc_info=True,
                )
                return error_msg

        # Build transfer payload with auto-detection of SIP vs phone number
        transfer_payload = self._build_transfer_payload(destination_number)

        try:
            # Make the POST request to transfer the call
            logger.debug(
                f"[VapiTool.call_transfer] Sending transfer request to {control_url} with destination {destination_number}"
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(control_url, json=transfer_payload)
                response.raise_for_status()

            logger.info(
                "[VapiTool.call_transfer] Successfully initiated call transfer",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "conversation_id": str(conversation_id),
                    "user_id": str(self.tool_metadata.user_id),
                    "call_id": call_id,
                    "destination_number": destination_number,
                    "purpose": purpose,
                },
            )
            return "Call has been transferred"

        except httpx.RequestError as e:
            error_msg = f"Network error occurred while transferring call: {e}"
            logger.error(
                f"[VapiTool.call_transfer] {error_msg}",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "conversation_id": str(conversation_id),
                    "user_id": str(self.tool_metadata.user_id),
                },
                exc_info=True,
            )
            return error_msg

        except httpx.HTTPStatusError as e:
            # Handle "Call Not Active" error gracefully - call has already ended
            if e.response.status_code == 400 and "Not Active" in e.response.text:
                logger.info(
                    "[VapiTool.call_transfer] Call is no longer active - call has likely ended",
                    extra={
                        "project_id": str(self.tool_metadata.project_id),
                        "account_name": self.tool_metadata.account_name,
                        "conversation_id": str(conversation_id),
                        "user_id": str(self.tool_metadata.user_id),
                        "call_id": call_id,
                    },
                )
                return "Call has already ended. Transfer is no longer possible."

            error_msg = f"HTTP error {e.response.status_code} occurred while transferring call: {e.response.text}"
            logger.error(
                f"[VapiTool.call_transfer] {error_msg}",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "conversation_id": str(conversation_id),
                    "user_id": str(self.tool_metadata.user_id),
                    "http_status_code": e.response.status_code,
                },
                exc_info=True,
            )
            return error_msg

        except Exception as e:
            error_msg = f"Unexpected error occurred while transferring call: {e}"
            logger.error(
                f"[VapiTool.call_transfer] {error_msg}",
                extra={
                    "project_id": str(self.tool_metadata.project_id),
                    "account_name": self.tool_metadata.account_name,
                    "conversation_id": str(conversation_id),
                    "user_id": str(self.tool_metadata.user_id),
                },
                exc_info=True,
            )
            return error_msg
