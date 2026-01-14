from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Channel,
    Message,
    Metadata,
    TextObject,
)
from services.relay_service import send_message
from utils.log import logger


class StoreMessagingTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        message_to_number: str,
    ) -> None:
        super().__init__(name="store_messaging_tool")
        self.tool_metadata = tool_metadata
        self.message_to_number = message_to_number

        self.register(self.send_text_message)

    @tool
    def send_text_message(self, message_content: str) -> str:
        """
        Send a text message to the store manager with customer phone and request details.

        This tool sends SMS notifications to store staff for follow-up. The customer's phone
        number is automatically included in the message.

        Args:
            message_content: Brief summary of the customer request. Keep it concise and factual.
                           Use abbreviated format when possible (e.g., "12/25" not "December 25th").
                           Recommended format: "RequestType: key details"

        Returns:
            Success confirmation or error message

        Technical Note: SMS has 160 char limit. Messages exceeding this will be split by carrier.
        Keep messages brief for best delivery. Customer phone is automatically prepended.
        """
        # Validate required phone numbers exist
        if not self.tool_metadata.customer_phone:
            logger.warning("No customer phone available for store messaging")
            return "Unable to send message: customer phone number not available"

        if not self.tool_metadata.store_phone:
            logger.warning("No store phone available for store messaging")
            return "Unable to send message: store phone number not configured"

        # Store validated phone numbers in local variables for type safety
        customer_phone: str = self.tool_metadata.customer_phone
        store_phone: str = self.tool_metadata.store_phone

        # Validate phone number format (+ followed by digits only)
        if not self._is_valid_phone(customer_phone):
            logger.error(f"Invalid customer phone format: {customer_phone}")
            return "Unable to send message: invalid customer phone number format"

        if not self._is_valid_phone(store_phone):
            logger.error(f"Invalid store phone format: {store_phone}")
            return "Unable to send message: invalid store phone number format"

        # Format the message with customer phone
        full_message = f"From: {customer_phone}\n{message_content}"

        # Log warning if message is long (will be split by Twilio)
        message_length = len(full_message)
        if message_length > 160:
            logger.warning(
                f"Message length {message_length} exceeds 160 chars. "
                f"Twilio will split into multiple SMS segments."
            )

        logger.debug(
            f"Sending store message to {self.message_to_number}: {full_message} "
            f"(length: {message_length} chars)"
        )

        message = Message(
            author_type=AuthorType.AGENT,
            sender_identifier=store_phone,
            recipient_identifier=self.message_to_number,
            channel=Channel.SMS,
            broker=Broker.TWILIO,
            text=TextObject(body=full_message),
            metadata=Metadata(testing=False),
        )

        try:
            response = send_message(message)
            if response.get("status") == "scheduled":
                logger.info(
                    f"Store message sent successfully to {self.message_to_number}"
                )
                return "Message sent to store manager for follow-up"
            else:
                error_msg = response.get("error_message", "Unknown error")
                logger.error(f"Failed to send store message: {error_msg}")
                return f"Failed to send message: {error_msg}"
        except Exception as e:
            logger.error(f"Exception sending store message: {str(e)}")
            return f"Error sending message: {str(e)}"

    def _is_valid_phone(self, phone: str) -> bool:
        """
        Validate phone number format for SMS sending.

        Required format: + followed by 1-15 digits (e.g., +14155551234)

        Args:
            phone: Phone number to validate

        Returns:
            True if valid phone format, False otherwise
        """
        if not phone or len(phone) < 2:
            return False

        # Must start with '+'
        if phone[0] != "+":
            return False

        # Rest must be digits only
        if not phone[1:].isdigit():
            return False

        # Valid international format allows 1-15 digits after the '+'
        if len(phone[1:]) < 1 or len(phone[1:]) > 15:
            return False

        return True
