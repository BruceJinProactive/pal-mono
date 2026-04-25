"""Tests for agent.memory._implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestGetAllMemories:
    @patch("agent.memory._implementation.get_client")
    @patch("agent.memory._implementation._get_cached_memories")
    async def test_cache_hit_returns_cached_value(
        self, mock_get_cached: MagicMock, mock_get_client: MagicMock
    ) -> None:
        from agent.memory._implementation import get_all_memories

        mock_get_cached.return_value = "cached memories about the user"
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = await get_all_memories("user-123")

        assert result == "cached memories about the user"
        mock_client.update_current_span.assert_called_once_with(
            metadata={"cache_hit": True}
        )

    @patch("agent.memory._implementation.get_client")
    @patch(
        "agent.memory._implementation._fetch_and_cache_memories",
        new_callable=AsyncMock,
    )
    @patch("agent.memory._implementation._get_cached_memories")
    async def test_cache_miss_returns_empty_and_triggers_background_fetch(
        self,
        mock_get_cached: MagicMock,
        mock_fetch: AsyncMock,
        mock_get_client: MagicMock,
    ) -> None:
        from agent.memory._implementation import get_all_memories

        mock_get_cached.return_value = None
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = await get_all_memories("user-456")

        assert result == ""
        mock_client.update_current_span.assert_called_once_with(
            metadata={"cache_hit": False}
        )
