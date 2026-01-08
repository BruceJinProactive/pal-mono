"""
Slack Message Sending Module

Provides a generic function for sending messages to Slack channels.
"""

from typing import Any, Dict, List, Optional

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from starlette.concurrency import run_in_threadpool

from utils.log import logger

from ._client import get_slack_client


async def send_slack_message(
    blocks: List[Dict[str, Any]],
    text_fallback: str = "New message",
    channel: Optional[str] = None,
    client: Optional[AsyncWebClient] = None,
    thread_ts: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a message to Slack with rich block formatting.

    Args:
        blocks: List of Slack block elements for rich formatting
        text_fallback: Fallback text for notifications
        channel: Target channel (uses default if not provided)
        client: Optional Slack client to reuse
        thread_ts: Optional thread timestamp for replies

    Returns:
        dict: {"status": "success"|"error", "message": str, "ts": str}
    """
    try:
        if not client:
            client = await run_in_threadpool(get_slack_client)

        target_channel = channel or "oncall"

        response = await client.chat_postMessage(
            channel=target_channel,
            text=text_fallback,
            blocks=blocks,
            thread_ts=thread_ts,
        )

        if response["ok"]:
            logger.info(f"[Slack] Block message sent to {target_channel}")
            return {
                "status": "success",
                "message": "Message sent successfully",
                "ts": response.get("ts"),
            }
        else:
            error_msg = response.get("error", "Unknown error")
            logger.error(f"[Slack] Failed to send block message: {error_msg}")
            return {"status": "error", "message": f"Slack API error: {error_msg}"}

    except SlackApiError as e:
        error_msg = e.response.get("error", str(e))
        logger.error(f"[Slack] API error: {error_msg}")
        return {"status": "error", "message": f"Slack API error: {error_msg}"}
    except Exception as e:
        logger.error(f"[Slack] Unexpected error: {e}")
        return {"status": "error", "message": str(e)}
