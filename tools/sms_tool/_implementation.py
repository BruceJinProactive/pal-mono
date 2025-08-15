from datetime import datetime, timezone
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from api.schemas.chat.message import AuthorType, Broker, Extras
from api.schemas.chat.message import Message as RelayMessage
from api.schemas.chat.message import Metadata, TextObject, Type
from db.tables.types import Channel
from services.relay_service import send_message as relay_send_message
from tools.sms_tool._llm import generate_order_summary
from tools.sms_tool.classes import Message, MessageType
from tools.utils.ordering._utils import get_chat_history
from utils.log import logger


class SMSTool(Toolkit):
    def __init__(
        self,
        sender_identifier: str,
        tool_metadata: ToolMetadata,
        default_phone_number: Optional[str] = None,
    ):
        super().__init__(name="sms_tool")

        # Log instance creation
        instance_id = id(self)
        logger.debug(f"SMSTool instance created: id={instance_id}")

        # Configs
        self.tool_metadata = tool_metadata
        self.sender_phone_number = sender_identifier
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Register tools
        self.register(self.send_order_summary)

    @tool
    def send_order_summary(
        self,
        recipient_phone_number: str,
    ) -> str:
        """
        Sends a summary of an order via SMS.

        Args:
            recipient_phone_number: Recipient's phone number.

        Returns:
            str: Success or error message
        """
        try:

            # Get chat history using query_messages_tool
            chat_history: str = get_chat_history(self.query_messages_tool)

            # Generate summary using LLM
            content = generate_order_summary(chat_history)
            if not content:
                return "Failed to generate order summary. Please try again."

            # Create and send message
            message = Message(
                type=MessageType.ORDER_SUMMARY,
                content=content,
                phone_number=recipient_phone_number,
            )

            return self._send_message(message)

        except Exception as e:
            logger.error(f"[SMSTool.send_order_summary] Error: {e}")
            return f"Failed to send order summary: {str(e)}"

    def _send_message(self, message: Message) -> str:
        """
        Internal method to send a message via SMS.

        Args:
            message (Message): The message to send

        Returns:
            str: Success or error message
        """
        try:
            # Create a Message object for the SMS
            relay_message = RelayMessage(
                author_type=AuthorType.SYSTEM,
                sender_identifier=self.sender_phone_number,
                recipient_identifier=message.phone_number,
                channel=Channel.SMS,
                broker=Broker.TWILIO,
                type=Type.TEXT,
                text=TextObject(body=message.content),
                metadata=Metadata(testing=False),
                extras=Extras(),
            )

            # Send the message through the relay service
            response = relay_send_message(
                relay_message, delivery_time=datetime.now(timezone.utc)
            )

            if response.get("status") == "scheduled":
                return "Message sent successfully."
            else:
                return f"Failed to send message: {response.get('error_message', 'Unknown error')}"

        except Exception as e:
            logger.error(f"[SMSTool._send_message] Error: {e}")
            return f"Failed to send message: {str(e)}"
