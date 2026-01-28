"""
Slack Client Management Module

Provides centralized Slack client creation and management.
"""

import os
import threading
import time
from typing import Dict, Optional, Tuple

from slack_sdk.web.async_client import AsyncWebClient

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Default Slack channel for all services
DEFAULT_SLACK_CHANNEL = "#test-channel"

# Global client instance for reuse
_client_instance: AsyncWebClient | None = None
# Thread lock for synchronizing client access
_client_lock = threading.Lock()

# User ID lookup cache: {name: (user_id, timestamp)}
# TTL: 1 hour (3600 seconds) - users change less frequently than channels
_USER_ID_CACHE: Dict[str, Tuple[Optional[str], float]] = {}
_USER_ID_CACHE_TTL = 3600


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


async def get_slack_user_id(name: str, slack_client: AsyncWebClient) -> Optional[str]:
    """
    Get the Slack user ID for a given name.

    Searches for users by display name or real name (case-insensitive).
    Uses a 1-hour cache to reduce Slack API calls.

    Args:
        name: The display name or real name to search for
        slack_client: Slack API client for looking up users

    Returns:
        Optional[str]: User ID if found, None otherwise
    """
    # Normalize cache key to lowercase for case-insensitive matching
    cache_key = name.lower().strip()

    # Check cache first
    current_time = time.time()
    if cache_key in _USER_ID_CACHE:
        user_id, cached_time = _USER_ID_CACHE[cache_key]
        if current_time - cached_time < _USER_ID_CACHE_TTL:
            logger.debug(f"[Slack] Using cached user ID for {name}: {user_id}")
            return user_id

    logger.debug(f"[Slack] Looking up user ID for: {name}")

    try:
        # Use users.list to search for the user
        cursor = None
        while True:
            if cursor:
                response = await slack_client.users_list(limit=200, cursor=cursor)
            else:
                response = await slack_client.users_list(limit=200)

            if not response["ok"]:
                logger.error(f"[Slack] Failed to list users: {response.get('error')}")
                return None

            # Search for matching user by display name or real name
            members = response.get("members", [])
            for member in members:
                if member.get("deleted") or member.get("is_bot"):
                    continue

                profile = member.get("profile", {})
                display_name = profile.get("display_name", "").lower()
                real_name = profile.get("real_name", "").lower()

                # Match against display name or real name (case-insensitive)
                if cache_key in [display_name, real_name]:
                    user_id = member["id"]
                    logger.info(f"[Slack] Found user {name} with ID {user_id}")
                    # Cache the result
                    _USER_ID_CACHE[cache_key] = (user_id, current_time)
                    return user_id

            # Check if there are more pages
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        logger.warning(f"[Slack] No user found with name {name}")
        # Cache the "not found" result to avoid repeated lookups
        _USER_ID_CACHE[cache_key] = (None, current_time)
        return None

    except Exception as e:
        logger.error(f"[Slack] Error looking up user {name}: {e}", exc_info=True)
        return None
