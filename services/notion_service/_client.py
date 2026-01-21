"""
Notion Client Management Module

Provides centralized Notion client creation and management.
"""

import os
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

    Uses a singleton pattern to reuse the same client instance.
    Fetches the API token from AWS Secrets Manager on first use.

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
            logger.debug("[Notion] Client instance created")

        return _client_instance


def get_notion_database_id() -> str:
    """
    Get the Notion database ID from environment variables.

    Returns:
        str: The Notion database ID

    Raises:
        ValueError: If database ID is not configured
    """
    database_id = os.environ.get("NOTION_DATABASE_ID")
    if not database_id:
        logger.error("[Notion] NOTION_DATABASE_ID not configured")
        raise ValueError("Notion database ID not configured")
    return database_id


def get_notion_feedback_database_id() -> str:
    """
    Get the Notion feedback database ID from environment variables.

    This is a separate database specifically for feedback tickets,
    distinct from the main sprint/project board.

    Returns:
        str: The Notion feedback database ID

    Raises:
        ValueError: If feedback database ID is not configured
    """
    database_id = os.environ.get("NOTION_FEEDBACK_DB_ID")
    if not database_id:
        logger.error("[Notion] NOTION_FEEDBACK_DB_ID not configured")
        raise ValueError("Notion feedback database ID not configured")
    return database_id


def reset_client() -> None:
    """
    Reset the cached Notion client instance.

    This is useful for testing or when credentials change.
    """
    global _client_instance
    with _client_lock:
        _client_instance = None
    logger.debug("[Notion] Client instance reset")
