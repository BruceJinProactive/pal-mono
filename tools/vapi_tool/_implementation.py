import os

import httpx
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from db.repositories import ConversationRepository
from db.session import SyncSessionLocal
from utils.log import logger


def _get_control_url_from_vapi(call_id: str) -> str:
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
        response = httpx.get(vapi_url, headers=headers, timeout=30.0)
        response.raise_for_status()

        call_data = response.json()
        control_url = call_data.get("monitor", {}).get("controlUrl")

        if not control_url:
            logger.error(
                "[VapiTool._get_control_url_from_vapi] No control URL found in Vapi call response"
            )
            raise Exception(
                "[VapiTool._get_control_url_from_vapi] No control URL found in Vapi call response"
            )

        return control_url

    except httpx.RequestError as e:
        logger.error(
            f"[VapiTool._get_control_url_from_vapi] Network error occurred while fetching call data from Vapi: {e}",
            exc_info=True,
        )
        raise Exception(
            f"[VapiTool._get_control_url_from_vapi] Network error occurred while fetching call data from Vapi: {e}"
        )

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[VapiTool._get_control_url_from_vapi] HTTP error {e.response.status_code} occurred while fetching call data from Vapi: {e.response.text}",
            exc_info=True,
        )
        raise Exception(
            f"[VapiTool._get_control_url_from_vapi] HTTP error {e.response.status_code} occurred while fetching call data from Vapi: {e.response.text}"
        )
    except Exception as e:
        logger.error(
            f"[VapiTool._get_control_url_from_vapi] Unexpected error occurred while fetching call data from Vapi: {e}",
            exc_info=True,
        )
        raise Exception(
            f"[VapiTool._get_control_url_from_vapi] Unexpected error occurred while fetching call data from Vapi: {e}"
        )


class VapiTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        destination_number: str,
        transfer_message: str | None = None,
    ):
        super().__init__(name="vapi_tool")
        self.tool_metadata = tool_metadata
        self.destination_number = destination_number
        self.transfer_message = (
            transfer_message
            or "I'll transfer you to our customer support. Just hang tight for a moment."
        )
        self.register(self.call_transfer)

    @tool
    def call_transfer(self) -> str:
        """
        Transfer the current call to another phone number.

        IMPORTANT: This tool is only available during voice calls and should NOT be used
        in text/message conversations. It will only function when the user is on an
        active voice call through the Vapi system.

        Returns:
            str: Success or error message about the call transfer attempt.
        """
        # Get control URL from the conversations table using session_id (conversation_id)
        conversation_id = self.tool_metadata.session_id
        # get last message, and get ctrl url from the message metadata
        if not conversation_id:
            error_msg = "No conversation ID available. Call transfer is not possible."
            logger.error(f"[VapiTool.call_transfer] {error_msg}")
            return error_msg
        db = SyncSessionLocal()

        # Get conversation and fetch control URL from Vapi API
        try:
            conversation_repo = ConversationRepository(db)
            conversation = conversation_repo.get_conversation_by_id(conversation_id)

            if not conversation:
                error_msg = f"Conversation {conversation_id} not found. Call transfer is not possible."
                logger.error(f"[VapiTool.call_transfer] {error_msg}")
                return error_msg

            call_id = conversation.call_id
            if not call_id:
                error_msg = "No call ID available for this conversation. Call transfer is not possible."
                logger.error(f"[VapiTool.call_transfer] {error_msg}")
                return error_msg

            control_url = _get_control_url_from_vapi(call_id)

        except Exception as e:
            error_msg = f"Error fetching call data: {e}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}", exc_info=True)
            return error_msg
        finally:
            db.close()

        transfer_payload = {
            "type": "transfer",
            "destination": {"type": "number", "number": self.destination_number},
            "content": self.transfer_message,
        }

        try:
            # Make the POST request to transfer the call
            response = httpx.post(control_url, json=transfer_payload, timeout=30.0)
            response.raise_for_status()

            logger.info(
                f"[VapiTool.call_transfer] Successfully initiated call transfer to {self.destination_number}"
            )
            return "Call has been transfered"

        except httpx.RequestError as e:
            error_msg = f"Network error occurred while transferring call: {e}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}", exc_info=True)
            return error_msg

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} occurred while transferring call: {e.response.text}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}", exc_info=True)
            return error_msg

        except Exception as e:
            error_msg = f"Unexpected error occurred while transferring call: {e}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}", exc_info=True)
            return error_msg
