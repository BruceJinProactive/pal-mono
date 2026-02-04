"""
Slack Bot Configuration Module

This module handles Slack Bolt app initialization, event handlers, and lifecycle management.
"""

import re
import threading

from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Global Slack app instance and thread safety
_slack_app = None
_slack_handler = None
_slack_init_lock = threading.Lock()


def get_slack_bot_token() -> str:
    """
    Get Slack bot token from secrets.

    Returns:
        str: Slack bot token

    Raises:
        ValueError: If Slack bot token not configured
    """
    try:
        bot_token = get_server_secret_with_fallback("SLACK_BOT_TOKEN")
        return bot_token
    except ValueError as e:
        logger.error(f"[Slackbot] SLACK_BOT_TOKEN not found: {e}")
        raise ValueError("Slack bot token not configured")


def create_slack_app() -> AsyncApp | None:
    """
    Create and configure Slack Bolt app with event handlers.

    Returns:
        AsyncApp | None: Configured Slack app or None if credentials not available
    """
    try:
        bot_token = get_server_secret_with_fallback("SLACK_BOT_TOKEN")
        signing_secret = get_server_secret_with_fallback("SLACK_SIGNING_SECRET")
    except ValueError as e:
        logger.warning(
            f"[Slackbot] Slack credentials not found: {e} - Event handling disabled"
        )
        return None

    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    # Import commands module here to avoid circular imports
    from . import _commands

    async def process_message(event, client):
        """Shared logic to process messages from both mentions and DMs."""
        message_text = event.get("text", "").lower()

        # Check for feedback-status command (must come before feedback check)
        if "feedback-status" in message_text:
            await _commands.handle_feedback_status_request(event, client)
        # Check for feedback command
        elif "feedback" in message_text:
            await _commands.handle_feedback_request(event, client)
        # Check for daily report
        elif "daily" in message_text:
            await _commands.handle_report_request("daily", event, client)
        # Check for weekly report
        elif "weekly" in message_text:
            await _commands.handle_report_request("weekly", event, client)
        # Check for monthly report
        elif "monthly" in message_text:
            await _commands.handle_report_request("monthly", event, client)
        # Check for last X hours
        elif re.search(r"last\s+\d+\s+hours?", message_text, re.IGNORECASE):
            await _commands.handle_last_hours_request(event, client)
        # Check for custom date range (with optional time: HH:MM)
        elif re.search(
            r"from\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?\s+to\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?",
            message_text,
            re.IGNORECASE,
        ):
            await _commands.handle_custom_date_request(event, client)
        else:
            # Unknown command - send simple error message
            channel = event.get("channel")
            error_text = "Please try again."
            await client.chat_postMessage(channel=channel, text=error_text, mrkdwn=True)

    # Register app_mention handler to only respond when bot is @mentioned
    @app.event("app_mention")
    async def handle_app_mention(event, client):
        """Handle all app mentions and route to appropriate handler."""
        await process_message(event, client)

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
            await process_message(event, client)

    return app


def _get_slack_handler() -> AsyncSlackRequestHandler | None:
    """
    Internal function to get the Slack request handler.
    Uses singleton pattern with thread-safe initialization.

    Returns:
        AsyncSlackRequestHandler | None: Handler instance or None if not configured
    """
    global _slack_app, _slack_handler

    if _slack_handler is None:
        with _slack_init_lock:
            # Double-check pattern to prevent race conditions
            if _slack_handler is None:
                _slack_app = create_slack_app()
                if _slack_app:
                    _slack_handler = AsyncSlackRequestHandler(_slack_app)

    return _slack_handler
