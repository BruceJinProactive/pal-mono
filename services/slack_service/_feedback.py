"""
Slack Feedback Notification Module

Provides functionality to send feedback notifications to Slack using Block Kit formatting.
"""

import os
from typing import Any, Dict, List, Optional

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from utils.log import logger

from ._client import get_slack_client


async def send_feedback_notification(
    client_name: str,
    user_email: str,
    tags: Optional[List[str]],
    feedback_text: Optional[str],
    conversation_id: str,
    reaction: Optional[str] = None,
    feedback_id: Optional[str] = None,
    client: Optional[AsyncWebClient] = None,
) -> Optional[Dict[str, Any]]:
    """
    Send a formatted feedback notification to Slack using Block Kit.

    This function sends a professional-looking feedback ticket to the configured
    Slack channel. It includes error handling to ensure that Slack API failures
    do not crash the application or rollback database transactions.

    Args:
        client_name: Name of the client/account
        user_email: Email of the user who submitted feedback
        tags: List of feedback tags (optional)
        feedback_text: The main feedback content (optional)
        conversation_id: ID of the conversation
        reaction: Feedback reaction (thumbs_up/thumbs_down) (optional)
        feedback_id: ID of the feedback entry (optional)
        client: Optional Slack client to reuse (creates new one if not provided)

    Returns:
        dict: Response from Slack API if successful, None if failed

    Note:
        - Uses SLACK_BOT_TOKEN from environment/secrets for authentication
        - Uses SLACK_CHANNEL_ID from environment for the target channel
        - Failures are logged but do not raise exceptions
    """
    try:
        # Get Slack client and channel
        if client is None:
            try:
                client = get_slack_client()
            except ValueError as e:
                logger.error(f"[Slack Feedback] Failed to get Slack client: {e}")
                return None

        channel_id = os.environ.get("SLACK_CHANNEL_ID")
        if not channel_id:
            logger.error("[Slack Feedback] SLACK_CHANNEL_ID not configured")
            return None

        # Build the emoji based on reaction
        reaction_emoji = ""
        if reaction == "thumbs_up":
            reaction_emoji = "👍 "
        elif reaction == "thumbs_down":
            reaction_emoji = "👎 "

        # Format tags for display
        tags_display = ", ".join(tags) if tags else "None"

        # Build Slack Block Kit message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{reaction_emoji}📣 New Feedback: {client_name}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*User:*\n{user_email}"},
                    {"type": "mrkdwn", "text": f"*Tags:*\n`{tags_display}`"},
                ],
            },
        ]

        # Add feedback text section if provided
        if feedback_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Feedback:*\n>{feedback_text}",
                    },
                }
            )

        # Add reaction if provided and no emoji was added to header
        if reaction and not reaction_emoji:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Reaction:*\n{reaction}"},
                }
            )

        # Add context section with conversation ID
        context_elements = [
            {"type": "mrkdwn", "text": f"Conversation ID: `{conversation_id}`"}
        ]
        if feedback_id:
            context_elements.append(
                {"type": "mrkdwn", "text": f"Feedback ID: `{feedback_id}`"}
            )

        blocks.append({"type": "context", "elements": context_elements})

        # Send the message to Slack
        response = await client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=f"New feedback from {client_name}",  # Fallback text for notifications
        )

        logger.info(
            "[Slack Feedback] Successfully sent feedback notification to Slack",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
                "feedback_id": feedback_id,
            },
        )

        # Return the response as a dict
        if hasattr(response, "data") and isinstance(response.data, dict):
            return response.data
        return {"ok": response.get("ok", True), "ts": response.get("ts")}

    except SlackApiError as e:
        logger.error(
            f"[Slack Feedback] Slack API error: {e.response['error']}",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
                "error_details": e.response,
            },
        )
        return None
    except Exception as e:
        logger.error(
            f"[Slack Feedback] Unexpected error sending feedback notification: {e}",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
            },
        )
        return None
