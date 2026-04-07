# pyright: reportCallIssue=false, reportAttributeAccessIssue=false
import uuid
from unittest.mock import patch

from agent.tool import ToolMetadata
from api.schemas.chat.message import Broker
from tools.store_messaging_tool import StoreMessagingTool


def _make_metadata(
    sip_provider: str | None = None, **overrides: object
) -> ToolMetadata:
    defaults: dict = {
        "agent_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "account_name": "Test Account",
        "user_id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "timezone": "America/Los_Angeles",
        "customer_phone": "+15551111111",
        "store_phone": "+15552222222",
        "channel": "voice",
        "sip_provider": sip_provider,
    }
    defaults.update(overrides)
    return ToolMetadata(**defaults)


def _make_tool(sip_provider: str | None = None) -> StoreMessagingTool:
    return StoreMessagingTool(
        tool_metadata=_make_metadata(sip_provider=sip_provider),
        message_to_number="+15553333333",
    )


class TestBrokerSelection:
    """Verify the tool selects the correct broker based on ToolMetadata.sip_provider."""

    @patch("tools.store_messaging_tool._implementation.send_message")
    def test_default_uses_twilio_broker(self, mock_send: object) -> None:
        mock_send.return_value = {"status": "scheduled"}  # type: ignore[union-attr]
        tool = _make_tool()
        tool.send_text_message("Test message")
        call_args = mock_send.call_args  # type: ignore[union-attr]
        message = call_args[0][0]
        assert message.broker == Broker.TWILIO

    @patch("tools.store_messaging_tool._implementation.send_message")
    def test_twilio_provider_uses_twilio_broker(self, mock_send: object) -> None:
        mock_send.return_value = {"status": "scheduled"}  # type: ignore[union-attr]
        tool = _make_tool(sip_provider="twilio")
        tool.send_text_message("Test message")
        call_args = mock_send.call_args  # type: ignore[union-attr]
        message = call_args[0][0]
        assert message.broker == Broker.TWILIO

    @patch("tools.store_messaging_tool._implementation.send_message")
    def test_pizzacloud_provider_uses_pizzacloud_broker(
        self, mock_send: object
    ) -> None:
        mock_send.return_value = {"status": "scheduled"}  # type: ignore[union-attr]
        tool = _make_tool(sip_provider="pizzacloud")
        tool.send_text_message("Test message")
        call_args = mock_send.call_args  # type: ignore[union-attr]
        message = call_args[0][0]
        assert message.broker == Broker.PIZZACLOUD

    @patch("tools.store_messaging_tool._implementation.send_message")
    def test_snet_provider_uses_snet_broker(self, mock_send: object) -> None:
        mock_send.return_value = {"status": "scheduled"}  # type: ignore[union-attr]
        tool = _make_tool(sip_provider="snet")
        tool.send_text_message("Test message")
        call_args = mock_send.call_args  # type: ignore[union-attr]
        message = call_args[0][0]
        assert message.broker == Broker.SNET

    @patch("tools.store_messaging_tool._implementation.send_message")
    def test_unknown_provider_falls_back_to_twilio(self, mock_send: object) -> None:
        mock_send.return_value = {"status": "scheduled"}  # type: ignore[union-attr]
        tool = _make_tool(sip_provider="unknown")
        tool.send_text_message("Test message")
        call_args = mock_send.call_args  # type: ignore[union-attr]
        message = call_args[0][0]
        assert message.broker == Broker.TWILIO
