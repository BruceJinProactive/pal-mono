import httpx
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from db import get_db
from db.repositories import ConversationRepository
from utils.log import logger


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
        if not conversation_id:
            error_msg = "No conversation ID available. Call transfer is not possible."
            logger.error(f"[VapiTool.call_transfer] {error_msg}")
            return error_msg
        db_generator = get_db()
        db = next(db_generator)

        # Query the database to get the vapi_control_url
        try:
            conversation_repo = ConversationRepository(db)
            conversation = conversation_repo.get_conversation_by_id(conversation_id)

            if not conversation:
                error_msg = f"Conversation {conversation_id} not found. Call transfer is not possible."
                logger.error(f"[VapiTool.call_transfer] {error_msg}")
                return error_msg

            control_url = conversation.vapi_control_url
            if not control_url:
                error_msg = "No Vapi control URL available for this conversation. Call transfer is not possible."
                logger.error(
                    f"[VapiTool.call_transfer] {error_msg}",
                    extra={
                        "conversation_id": conversation_id,
                    },
                )
                return error_msg

        except Exception as e:
            error_msg = f"Error retrieving conversation data: {e}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}")
            return error_msg

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
            logger.error(f"[VapiTool.call_transfer] {error_msg}")
            return error_msg

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} occurred while transferring call: {e.response.text}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}")
            return error_msg

        except Exception as e:
            error_msg = f"Unexpected error occurred while transferring call: {e}"
            logger.error(f"[VapiTool.call_transfer] {error_msg}")
            return error_msg
