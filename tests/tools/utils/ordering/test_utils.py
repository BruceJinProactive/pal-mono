"""Tests for tools.utils.ordering._utils."""

from unittest.mock import MagicMock, patch

import pytest


class TestGetChatHistory:
    @patch("tools.utils.ordering._utils.get_client")
    def test_returns_history_and_updates_span(self, mock_get_client: MagicMock) -> None:
        from tools.utils.ordering._utils import get_chat_history

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_tool = MagicMock()
        mock_tool.query_messages.return_value = "User: I want pizza\nAgent: What size?"

        result = get_chat_history(mock_tool)

        assert "pizza" in result
        mock_client.update_current_span.assert_called_once_with(
            output="User: I want pizza\nAgent: What size?"
        )

    def test_raises_on_error_in_chat_history(self) -> None:
        from tools.utils.ordering._utils import get_chat_history

        mock_tool = MagicMock()
        mock_tool.query_messages.return_value = "Error in getting chat history"

        with pytest.raises(ValueError, match="Possible issue with chat history"):
            get_chat_history(mock_tool)
