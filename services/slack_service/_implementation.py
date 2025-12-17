"""
Core Slack Service Implementation

This module provides the core functionality for Slack integration:
- Event handling
- Message routing to handlers
- Generic message sending
"""

import re

from fastapi.responses import JSONResponse, Response
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from utils.log import logger

from ._client import get_slack_handler


async def handle_slack_events(request) -> Response:
    """
    Handle all Slack events by passing untouched request to Slack Bolt handler.
    This allows proper signature verification and URL verification by Slack Bolt.

    Args:
        request: FastAPI Request object (untouched - no request.json() called)

    Returns:
        FastAPI Response object from Slack Bolt handler
    """
    try:
        # Get Slack handler and let it handle everything (including URL verification)
        # Important: Don't call request.json() as it breaks Bolt's signature verification
        handler = get_slack_handler()
        if handler:
            return await handler.handle(request)
        else:
            logger.error("[Slackbot] Slack handler not configured")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "message": "Slack handler not configured"},
            )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling Slack event: {e}")
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e)}
        )


async def send_message(
    channel: str,
    text: str,
    blocks: list | None = None,
    thread_ts: str | None = None,
    client: AsyncWebClient | None = None,
) -> dict:
    """
    Send a generic message to Slack channel.

    Args:
        channel: Slack channel ID or name
        text: Plain text message (fallback for notifications)
        blocks: Optional Slack blocks for rich formatting
        thread_ts: Optional thread timestamp to reply in thread
        client: Optional Slack client (creates new one if not provided)

    Returns:
        dict: {"status": "success"|"error", "message": str}
    """
    try:
        # Get client if not provided
        if client is None:
            from ._client import get_client

            client = get_client()
            if client is None:
                return {
                    "status": "error",
                    "message": "Slack client not configured",
                }

        # At this point, client is guaranteed to be non-None
        assert client is not None  # Type hint for static analysis

        # Prepare message parameters
        post_params: dict = {
            "channel": channel,
            "text": text,
        }

        if blocks:
            post_params["blocks"] = blocks

        if thread_ts:
            post_params["thread_ts"] = thread_ts

        # Send message
        response = await client.chat_postMessage(**post_params)

        if response["ok"]:
            logger.info(f"[Slackbot] Message sent successfully to {channel}")
            return {
                "status": "success",
                "message": f"Message sent to {channel} successfully",
            }
        else:
            error_msg = response.get("error", "Unknown error")
            logger.error(f"[Slackbot] Slack API error: {error_msg}")
            return {
                "status": "error",
                "message": f"Failed to send to Slack: {error_msg}",
            }

    except SlackApiError as e:
        error_msg = f"Slack API error: {e.response['error']}"
        logger.error(f"[Slackbot] {error_msg}")
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Failed to send message: {str(e)}"
        logger.error(f"[Slackbot] {error_msg}")
        return {"status": "error", "message": error_msg}


async def get_channel_info(
    channel_id: str, client: AsyncWebClient | None = None
) -> dict | None:
    """
    Get channel information from Slack.

    Args:
        channel_id: Slack channel ID
        client: Optional Slack client (creates new one if not provided)

    Returns:
        dict: Channel info or None if failed
    """
    try:
        # Get client if not provided
        if client is None:
            from ._client import get_client

            client = get_client()
            if client is None:
                logger.error("[Slackbot] Slack client not configured")
                return None

        # At this point, client is guaranteed to be non-None
        assert client is not None  # Type hint for static analysis

        response = await client.conversations_info(channel=channel_id)
        if response and response.get("ok"):
            return response.get("channel")
        return None

    except Exception as e:
        logger.error(f"[Slackbot] Failed to get channel info for {channel_id}: {e}")
        return None


async def process_message(event, client):
    """
    Process incoming Slack messages and route to appropriate handler.

    This function is called by the Slack bot for all incoming messages
    (both @mentions and direct messages).

    Args:
        event: Slack message event
        client: Slack AsyncWebClient
    """
    message_text = event.get("text", "").lower()

    # Import analytics handler functions
    from .handlers.analytics import (
        handle_custom_date_request,
        handle_last_hours_request,
        handle_report_request,
    )

    # Check for daily report
    if "daily" in message_text:
        await handle_report_request("daily", event, client)
    # Check for weekly report
    elif "weekly" in message_text:
        await handle_report_request("weekly", event, client)
    # Check for monthly report
    elif "monthly" in message_text:
        await handle_report_request("monthly", event, client)
    # Check for last X hours
    elif re.search(r"last\s+\d+\s+hours?", message_text, re.IGNORECASE):
        await handle_last_hours_request(event, client)
    # Check for custom date range (with optional time: HH:MM)
    elif re.search(
        r"from\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?\s+to\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?",
        message_text,
        re.IGNORECASE,
    ):
        await handle_custom_date_request(event, client)
    else:
        # Unknown command - send simple error message
        channel = event.get("channel")
        error_text = "Please try again."
        await client.chat_postMessage(channel=channel, text=error_text, mrkdwn=True)
