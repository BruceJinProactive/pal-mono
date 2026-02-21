"""
Notion Client Management Module

Provides centralized Notion client creation and management.
"""

import threading

from notion_client import AsyncClient

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Global client instance for reuse
_client_instance: AsyncClient | None = None
# Thread lock for synchronizing client access
_client_lock = threading.Lock()


def get_notion_client() -> AsyncClient:
    """
    Get or create a Notion async client instance.

    Returns:
        AsyncClient: Configured Notion client

    Raises:
        ValueError: If no token available
    """
    global _client_instance

    # Use cached client if available, with thread safety
    with _client_lock:
        if _client_instance is None:
            try:
                api_key = get_server_secret_with_fallback("NOTION_API_KEY")
            except ValueError as e:
                logger.error(f"[Notion] Failed to get API key: {e}")
                raise ValueError("Notion API key not configured") from e

            _client_instance = AsyncClient(auth=api_key)

        return _client_instance


def reset_client() -> None:
    """
    Reset the cached Notion client instance.

    This is useful for testing or when credentials change.
    """
    global _client_instance
    with _client_lock:
        _client_instance = None
