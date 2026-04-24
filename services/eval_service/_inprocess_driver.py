"""InProcessDriver — calls get_chat_response_async directly, no HTTP.

Implements the AgentDriver protocol from pal-agents so it can be used
with the eval runner. Each turn opens its own AsyncSessionLocal.
"""

from __future__ import annotations

from pal_agents.evals.drivers.protocol import ConversationTurn, TurnResult
from pal_agents.input import RuntimeContext

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject, Type
from db.session import AsyncSessionLocal
from db.tables.types import Channel
from services.message_service import get_chat_response_async
from utils.log import logger
from utils.request_context import RequestContext


class InProcessDriver:
    """Driver that calls the chat service in-process.

    No HTTP round-trip, no URL config. Works on any environment automatically.
    """

    def __init__(
        self,
        recipient_identifier: str,
        sender_identifier: str = "eval-user@test.com",
        channel: str = "api",
        customer_phone: str | None = None,
    ) -> None:
        self.recipient_identifier = recipient_identifier
        self.sender_identifier = sender_identifier
        self.channel = Channel(channel)
        self.last_conversation_id: str | None = None
        self.customer_phone = customer_phone

    async def send_turn(
        self,
        message: str,
        conversation_history: list[ConversationTurn],
    ) -> TurnResult:
        """Send a user message directly to the chat service.

        Args:
            message: The user message to send.
            conversation_history: Previous turns (unused — chat service
                manages its own history via DB).

        Returns:
            TurnResult with the agent's response content.
        """
        chat_message = self._build_message(message)

        phone = self.customer_phone

        def _context_modifier(ctx: RuntimeContext) -> None:
            if phone:
                ctx.customer_phone = phone

        async with AsyncSessionLocal() as session:
            try:
                request_context = RequestContext()
                response_messages = await get_chat_response_async(
                    session=session,
                    message=chat_message,
                    request_context=request_context,
                    context_modifier=_context_modifier,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "InProcessDriver.send_turn failed",
                    extra={"recipient": self.recipient_identifier},
                )
                raise

        self.last_conversation_id = self._get_conversation_id(response_messages)
        content = self._extract_response_text(response_messages)
        return TurnResult(content=content)

    def _build_message(self, text: str) -> Message:
        """Construct a Message matching the chat API contract."""
        return Message(
            author_type=AuthorType.USER,
            sender_identifier=self.sender_identifier,
            recipient_identifier=self.recipient_identifier,
            channel=self.channel,
            type=Type.TEXT,
            text=TextObject(body=text),
            metadata=Metadata(testing=True),
        )

    @staticmethod
    def _get_conversation_id(response_messages: list[Message]) -> str | None:
        """Extract conversation_id from response metadata.session_id."""
        for msg in response_messages:
            if msg.metadata and msg.metadata.session_id:
                return msg.metadata.session_id
        return None

    @staticmethod
    def _extract_response_text(response_messages: list[Message]) -> str:
        """Extract agent response text from chat service response."""
        for msg in reversed(response_messages):
            if msg.author_type == AuthorType.AGENT and msg.text:
                return msg.text.body
        if response_messages and response_messages[0].text:
            return response_messages[0].text.body
        return "[No response content]"
