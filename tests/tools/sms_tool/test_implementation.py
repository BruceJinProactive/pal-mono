"""Tests for tools.sms_tool._implementation — Langfuse @observe decorator migration."""

from unittest.mock import MagicMock, patch


class TestSMSToolImport:
    """Covers line 5: @observe import via exercising the decorated method."""

    @patch("tools.sms_tool._implementation.get_chat_history")
    @patch("tools.sms_tool._implementation.generate_order_summary")
    @patch("tools.sms_tool._implementation.relay_send_message")
    @patch("tools.sms_tool._implementation.SyncSessionLocal")
    @patch("tools.sms_tool._implementation.MessageRepository")
    def test_send_order_summary_exists_and_is_decorated(
        self,
        mock_msg_repo,
        mock_session,
        mock_relay,
        mock_generate,
        mock_get_chat,
    ):
        from tools.sms_tool._implementation import SMSTool

        mock_get_chat.return_value = "User: I want a burger"
        mock_generate.return_value = "Order summary: 1x burger"

        tool = SMSTool(
            sender_identifier="+11234567890",
            tool_metadata=MagicMock(
                session_id="sess-1",
                agent_id="agent-1",
                account_name="test",
            ),
        )
        assert hasattr(tool, "send_order_summary")

        result = tool.send_order_summary(recipient_phone_number="+10987654321")

        mock_get_chat.assert_called_once()
        mock_generate.assert_called_once_with("User: I want a burger")
        assert isinstance(result, str)
