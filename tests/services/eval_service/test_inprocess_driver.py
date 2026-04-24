"""Tests for services/eval_service/_inprocess_driver.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.chat.message import AuthorType, Message, Metadata, TextObject
from services.eval_service._inprocess_driver import InProcessDriver

MODULE = "services.eval_service._inprocess_driver"


def _make_agent_message(body: str, session_id: str = "") -> Message:
    """Create a mock agent response message."""
    msg = MagicMock(spec=Message)
    msg.author_type = AuthorType.AGENT
    msg.text = TextObject(body=body)
    msg.metadata = Metadata(session_id=session_id) if session_id else None
    return msg


def _make_user_message(body: str) -> Message:
    """Create a mock user message."""
    msg = MagicMock(spec=Message)
    msg.author_type = AuthorType.USER
    msg.text = TextObject(body=body)
    msg.metadata = None
    return msg


class TestSendTurn:
    @pytest.fixture
    def driver(self) -> InProcessDriver:
        return InProcessDriver(
            recipient_identifier="project-123",
            sender_identifier="test@eval.com",
        )

    @pytest.mark.asyncio
    async def test_returns_agent_response(self, driver: InProcessDriver) -> None:
        agent_msg = _make_agent_message("Hello! How can I help?")
        mock_get_chat = AsyncMock(return_value=[agent_msg])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await driver.send_turn("Hi there", [])

        assert result.content == "Hello! How can I help?"
        mock_get_chat.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_extracts_last_agent_message(self, driver: InProcessDriver) -> None:
        """When multiple messages, extract last agent message."""
        user_msg = _make_user_message("Hi")
        agent_msg1 = _make_agent_message("First response", session_id="conv-1")
        agent_msg2 = _make_agent_message("Second response", session_id="conv-1")
        mock_get_chat = AsyncMock(return_value=[user_msg, agent_msg1, agent_msg2])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await driver.send_turn("Hi", [])

        assert result.content == "Second response"

    @pytest.mark.asyncio
    async def test_rolls_back_on_error(self, driver: InProcessDriver) -> None:
        mock_get_chat = AsyncMock(side_effect=ValueError("boom"))
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
            patch(f"{MODULE}.logger"),
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="boom"):
                await driver.send_turn("Hi", [])

        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_response_returns_placeholder(
        self, driver: InProcessDriver
    ) -> None:
        mock_get_chat = AsyncMock(return_value=[])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await driver.send_turn("Hi", [])

        assert result.content == "[No response content]"


class TestCustomerPhone:
    def test_stores_customer_phone(self) -> None:
        driver = InProcessDriver(
            recipient_identifier="proj",
            customer_phone="5551234567",
        )
        assert driver.customer_phone == "5551234567"

    def test_customer_phone_defaults_to_none(self) -> None:
        driver = InProcessDriver(recipient_identifier="proj")
        assert driver.customer_phone is None

    @pytest.mark.asyncio
    async def test_context_modifier_passed_to_service(self) -> None:
        driver = InProcessDriver(
            recipient_identifier="proj",
            customer_phone="5551234567",
        )
        agent_msg = _make_agent_message("Hi", session_id="conv-1")
        mock_get_chat = AsyncMock(return_value=[agent_msg])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await driver.send_turn("Hi", [])

        call_kwargs = mock_get_chat.call_args.kwargs
        assert "context_modifier" in call_kwargs
        assert call_kwargs["context_modifier"] is not None

    @pytest.mark.asyncio
    async def test_context_modifier_sets_customer_phone(self) -> None:
        from pal_agents.input import RuntimeContext

        driver = InProcessDriver(
            recipient_identifier="proj",
            customer_phone="5551234567",
        )
        agent_msg = _make_agent_message("Hi", session_id="conv-1")
        mock_get_chat = AsyncMock(return_value=[agent_msg])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await driver.send_turn("Hi", [])

        # Extract the modifier and verify it sets customer_phone
        modifier = mock_get_chat.call_args.kwargs["context_modifier"]
        ctx = RuntimeContext(timezone="UTC", channel="api")
        modifier(ctx)
        assert ctx.customer_phone == "5551234567"

    @pytest.mark.asyncio
    async def test_context_modifier_noop_when_no_phone(self) -> None:
        from pal_agents.input import RuntimeContext

        driver = InProcessDriver(recipient_identifier="proj")
        agent_msg = _make_agent_message("Hi", session_id="conv-1")
        mock_get_chat = AsyncMock(return_value=[agent_msg])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await driver.send_turn("Hi", [])

        modifier = mock_get_chat.call_args.kwargs["context_modifier"]
        ctx = RuntimeContext(timezone="UTC", channel="api")
        modifier(ctx)
        assert ctx.customer_phone is None


class TestBuildMessage:
    def test_message_fields(self) -> None:
        driver = InProcessDriver(
            recipient_identifier="project-456",
            sender_identifier="eval@test.com",
        )
        msg = driver._build_message("Hello world")

        assert msg.author_type == AuthorType.USER
        assert msg.sender_identifier == "eval@test.com"
        assert msg.recipient_identifier == "project-456"
        assert msg.text is not None
        assert msg.text.body == "Hello world"
        assert msg.metadata is not None
        assert msg.metadata.testing is True

    def test_channel_is_api(self) -> None:
        from db.tables.types import Channel

        driver = InProcessDriver(recipient_identifier="proj")
        msg = driver._build_message("test")
        assert msg.channel == Channel.API


class TestExtractResponseText:
    def test_extracts_agent_text(self) -> None:
        msg = _make_agent_message("Agent says hi")
        assert InProcessDriver._extract_response_text([msg]) == "Agent says hi"

    def test_falls_back_to_first_message(self) -> None:
        user_msg = _make_user_message("Echo")
        assert InProcessDriver._extract_response_text([user_msg]) == "Echo"

    def test_empty_list_returns_placeholder(self) -> None:
        assert InProcessDriver._extract_response_text([]) == "[No response content]"


class TestGetConversationId:
    def test_extracts_session_id_from_metadata(self) -> None:
        msg = _make_agent_message("Hi", session_id="conv-abc-123")
        assert InProcessDriver._get_conversation_id([msg]) == "conv-abc-123"

    def test_returns_none_when_no_metadata(self) -> None:
        msg = MagicMock(spec=Message)
        msg.metadata = None
        assert InProcessDriver._get_conversation_id([msg]) is None

    def test_returns_none_for_empty_session_id(self) -> None:
        msg = _make_agent_message("Hi", session_id="")
        assert InProcessDriver._get_conversation_id([msg]) is None

    def test_returns_none_for_empty_list(self) -> None:
        assert InProcessDriver._get_conversation_id([]) is None

    def test_skips_messages_without_metadata(self) -> None:
        msg_no_meta = MagicMock(spec=Message)
        msg_no_meta.metadata = None
        msg_with_meta = _make_agent_message("Hi", session_id="conv-456")
        assert (
            InProcessDriver._get_conversation_id([msg_no_meta, msg_with_meta])
            == "conv-456"
        )


class TestSendTurnConversationId:
    @pytest.fixture
    def driver(self) -> InProcessDriver:
        return InProcessDriver(
            recipient_identifier="project-123",
            sender_identifier="test@eval.com",
        )

    @pytest.mark.asyncio
    async def test_sets_last_conversation_id(self, driver: InProcessDriver) -> None:
        agent_msg = _make_agent_message("Hello!", session_id="conv-xyz-789")
        mock_get_chat = AsyncMock(return_value=[agent_msg])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            assert driver.last_conversation_id is None
            await driver.send_turn("Hi", [])

        assert driver.last_conversation_id == "conv-xyz-789"

    @pytest.mark.asyncio
    async def test_last_conversation_id_none_when_no_metadata(
        self, driver: InProcessDriver
    ) -> None:
        agent_msg = _make_agent_message("Hello!")
        mock_get_chat = AsyncMock(return_value=[agent_msg])
        mock_session = AsyncMock()

        with (
            patch(f"{MODULE}.get_chat_response_async", mock_get_chat),
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await driver.send_turn("Hi", [])

        assert driver.last_conversation_id is None
