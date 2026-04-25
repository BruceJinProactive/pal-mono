"""Tests for agent.storage._implementation."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestQueryHistoryMessages:
    @patch("agent.storage._implementation.get_client")
    @patch("agent.storage._implementation.AsyncSessionLocal")
    @patch("agent.storage._implementation.MessageRepositoryAsync")
    async def test_parses_messages_and_updates_span(
        self,
        mock_repo_cls: MagicMock,
        mock_session_local: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from agent.storage._implementation import query_history_messages

        # Set up mock DB messages
        msg1 = MagicMock()
        msg1.body = {
            "author_type": "user",
            "text": {"body": "Hello"},
            "context": "",
            "channel": "voice",
            "sender_identifier": "+15551234567",
        }
        msg2 = MagicMock()
        msg2.body = {
            "author_type": "agent",
            "text": {"body": "Hi there!"},
            "context": "",
            "channel": "voice",
            "sender_identifier": "agent",
        }

        mock_repo = AsyncMock()
        mock_repo.get_messages_by_conversation.return_value = [msg1, msg2]
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        conversation_id = uuid.uuid4()
        result = await query_history_messages(conversation_id)

        assert len(result) == 2
        assert result[0].role == "user"
        assert result[0].content == "Hello"
        assert result[1].role == "assistant"
        mock_client.update_current_span.assert_called_once()
        metadata = mock_client.update_current_span.call_args[1]["metadata"]
        assert metadata["history_messages"] == 2
        assert metadata["conversation_id"] == conversation_id

    @patch("agent.storage._implementation.get_client")
    @patch("agent.storage._implementation.AsyncSessionLocal")
    @patch("agent.storage._implementation.MessageRepositoryAsync")
    async def test_empty_conversation_returns_empty_list(
        self,
        mock_repo_cls: MagicMock,
        mock_session_local: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from agent.storage._implementation import query_history_messages

        mock_repo = AsyncMock()
        mock_repo.get_messages_by_conversation.return_value = []
        mock_repo_cls.return_value = mock_repo

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = await query_history_messages(uuid.uuid4())

        assert result == []
        metadata = mock_client.update_current_span.call_args[1]["metadata"]
        assert metadata["history_messages"] == 0
