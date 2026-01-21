"""
Slack Client Management Module

Provides centralized Slack client creation and management.
"""

import os
import threading

from slack_sdk.web.async_client import AsyncWebClient

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Default Slack channel for all services
DEFAULT_SLACK_CHANNEL = "#test-channel"

# Global client instance for reuse
_client_instance: AsyncWebClient | None = None
# Thread lock for synchronizing client access
_client_lock = threading.Lock()


def get_slack_client() -> AsyncWebClient:
    """
    Get or create a Slack async client instance.

    Uses a singleton pattern to reuse the same client instance.
    Fetches the bot token from AWS Secrets Manager on first use.

    Returns:
        AsyncWebClient: Configured Slack client

    Raises:
        ValueError: If no token available
    """
    global _client_instance

    # Use cached client if available, with thread safety
    with _client_lock:
        if _client_instance is None:
            try:
                bot_token = get_server_secret_with_fallback("SLACK_BOT_TOKEN")
            except ValueError as e:
                logger.error(f"[Slack] Failed to get bot token: {e}")
                raise ValueError("Slack bot token not configured")

            _client_instance = AsyncWebClient(token=bot_token)

        return _client_instance


def get_slack_channel_from_env_key(env_key: str) -> str:
    """
    Get a Slack channel from a specific environment variable.

    Args:
        env_key: The environment variable key to look up (e.g., "SLACK_CHANNEL_INTEGRATIONS")

    Returns:
        str: Channel name with # prefix from the environment variable, or default channel if not found
    """
    channel = os.environ.get(env_key)
    if channel:
        # Ensure channel starts with #
        if not channel.startswith("#"):
            channel = f"#{channel}"
        logger.debug(f"[Slack] Using channel {channel} from {env_key}")
        return channel
    else:
        logger.debug(f"[Slack] {env_key} not configured, using default channel")
        return DEFAULT_SLACK_CHANNEL


def reset_client() -> None:
    """
    Reset the cached Slack client instance.

    This is useful for testing or when credentials change.
    """
    global _client_instance
    with _client_lock:
        _client_instance = None
    logger.debug("[Slack] Client instance reset")
