"""
Slack Client Management

This module handles Slack bot lifecycle including:
- Bot app initialization
- Credential management
- Thread-safe singleton pattern for bot instance
"""

import threading

from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from utils.log import logger
from utils.secret import get_client_secret_with_fallback

# Global Slack app instance and thread safety
_slack_app = None
_slack_handler = None
_slack_init_lock = threading.Lock()


def get_slack_credentials() -> tuple[str, str]:
    """Get Slack bot token and channel from secrets."""
    try:
        bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
    except ValueError as e:
        logger.error(f"[Slackbot] SLACK_BOT_TOKEN not found: {e}")
        raise ValueError("Slack bot token not configured")

    try:
        slack_channel = get_client_secret_with_fallback("SLACK_CHANNEL")
    except ValueError:
        slack_channel = "#test-channel"  # Default fallback

    return bot_token, slack_channel


def create_slack_app(message_processor=None):
    """
    Create and configure Slack Bolt app with event handlers.

    Args:
        message_processor: Optional async function(event, client) to process messages.
                          If None, basic error message is returned.

    Returns:
        AsyncApp instance or None if credentials not found
    """
    try:
        bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
        signing_secret = get_client_secret_with_fallback("SLACK_SIGNING_SECRET")
    except ValueError as e:
        logger.warning(
            f"[Slackbot] Slack credentials not found: {e} - Event handling disabled"
        )
        return None

    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    async def default_processor(event, client):
        """Default message processor when none provided."""
        channel = event.get("channel")
        error_text = "Please try again."
        await client.chat_postMessage(channel=channel, text=error_text, mrkdwn=True)

    processor = message_processor or default_processor

    # Register app_mention handler to only respond when bot is @mentioned
    @app.event("app_mention")
    async def handle_app_mention(event, client):
        """Handle all app mentions and route to appropriate handler."""
        await processor(event, client)

    # Register message handler to respond to direct messages only
    @app.event("message")
    async def handle_message(event, client, say):
        """Handle direct messages to the bot only (not public channels)."""
        # Only respond to direct messages, not public channel messages
        # In DMs, channel_type is "im" (instant message)
        # In public channels, channel_type is "channel"
        # In private channels, channel_type is "group"
        channel_type = event.get("channel_type")

        # Only process if it's a direct message AND not from a bot
        if (
            channel_type == "im"
            and event.get("subtype") is None
            and event.get("bot_id") is None
        ):
            await processor(event, client)

    return app


def get_slack_handler():
    """
    Get the Slack request handler (singleton pattern).

    Returns:
        AsyncSlackRequestHandler instance or None if not configured
    """
    global _slack_app, _slack_handler

    if _slack_handler is None:
        with _slack_init_lock:
            # Double-check pattern to prevent race conditions
            if _slack_handler is None:
                # Import here to avoid circular dependency
                from ._implementation import process_message

                _slack_app = create_slack_app(message_processor=process_message)
                if _slack_app:
                    _slack_handler = AsyncSlackRequestHandler(_slack_app)

    return _slack_handler


def get_client() -> AsyncWebClient | None:
    """
    Get Slack AsyncWebClient for making API calls.

    Returns:
        AsyncWebClient instance or None if credentials not configured
    """
    try:
        bot_token, _ = get_slack_credentials()
        return AsyncWebClient(token=bot_token)
    except ValueError:
        return None
