"""Tests for agent.tool.internal.query_messages_tool._implementation."""

import uuid
from unittest.mock import MagicMock, patch

from agent.tool._config import ToolMetadata


def _make_metadata() -> ToolMetadata:
    return ToolMetadata(
        agent_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        account_name="Test Account",
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        timezone="America/Los_Angeles",
        customer_phone="+15551111111",
        store_phone="+15552222222",
        channel="voice",
    )


class TestQueryMessagesTool:
    @patch("agent.tool.internal.query_messages_tool._implementation.get_client")
    @patch("agent.tool.internal.query_messages_tool._implementation.get_db")
    @patch(
        "agent.tool.internal.query_messages_tool._implementation.MessageRepository",
    )
    def test_formats_history_and_updates_span_twice(
        self,
        mock_repo_cls: MagicMock,
        mock_get_db: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from agent.tool.internal.query_messages_tool._implementation import (
            QueryMessagesTool,
        )

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        msg1 = MagicMock()
        msg1.body = {
            "author_type": "user",
            "text": {"body": "I want a large pepperoni"},
        }
        msg2 = MagicMock()
        msg2.body = {
            "author_type": "agent",
            "text": {"body": "Sure, anything else?"},
        }
        mock_repo_cls.return_value.get_messages_by_conversation.return_value = [
            msg1,
            msg2,
        ]

        tool = QueryMessagesTool(metadata=_make_metadata())
        result = tool.query_messages()

        assert "large pepperoni" in result
        assert "anything else" in result

        # First call: metadata span, second call: output span
        assert mock_client.update_current_span.call_count == 2
        first_call = mock_client.update_current_span.call_args_list[0]
        assert "metadata" in first_call[1]
        second_call = mock_client.update_current_span.call_args_list[1]
        assert "output" in second_call[1]
