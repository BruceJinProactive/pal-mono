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

# Client-specific Slack channel routing
CLIENT_CHANNEL_MAP = {
    # "Client A": "C0A8UD7J9D1",
}


def get_feedback_channel_for_client(client_name: str) -> Optional[str]:
    """Get the Slack channel ID for a specific client's feedback."""
    normalized_name = client_name.strip()
    return CLIENT_CHANNEL_MAP.get(normalized_name)


async def send_feedback_notification(
    client_name: str,
    user_email: str,
    tags: Optional[List[str]],
    feedback_text: Optional[str],
    conversation_id: str,
    conversation_link: Optional[str] = None,
    notion_ticket_url: Optional[str] = None,
    notion_page_id: Optional[str] = None,
    user_name: Optional[str] = None,
    reaction: Optional[str] = None,
    feedback_id: Optional[str] = None,
    channel_override: Optional[str] = None,
    client: Optional[AsyncWebClient] = None,
) -> Optional[Dict[str, Any]]:
    """
    Send a formatted feedback notification to Slack using Block Kit.
    """
    try:
        # Get Slack client and channel
        if client is None:
            try:
                client = get_slack_client()
            except ValueError as e:
                logger.error(f"[Slack Feedback] Failed to get Slack client: {e}")
                return None

        # Use channel override if provided, otherwise use default
        if channel_override:
            channel_id = channel_override
        else:
            channel_id = get_feedback_channel_for_client(client_name) or os.environ.get(
                "SLACK_CHANNEL_ID"
            )

        if not channel_id:
            logger.error("[Slack Feedback] No Slack channel configured")
            return None

        # Build the emoji based on reaction
        reaction_emoji = ""
        if reaction == "thumbs_up":
            reaction_emoji = "👍 "
        elif reaction == "thumbs_down":
            reaction_emoji = "👎 "

        # --- BLOCK 1: Header ---
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{reaction_emoji}New Feedback from {client_name}",
                    "emoji": True,
                },
            }
        ]

        # --- BLOCK 2: Compact Metadata (User, Email, Tags) ---
        # Using 'fields' creates a nice two-column grid layout
        fields = []

        # User Info
        if user_name:
            fields.append({"type": "mrkdwn", "text": f"*User:*\n{user_name}"})
        if user_email:
            fields.append({"type": "mrkdwn", "text": f"*Email:*\n{user_email}"})

        # Tags (formatted as badges)
        if tags:
            tags_display = " ".join([f"`{tag}`" for tag in tags])
            fields.append({"type": "mrkdwn", "text": f"*Tags:*\n{tags_display}"})

        # Add the fields section if we have data
        if fields:
            blocks.append({"type": "section", "fields": fields})

        # --- BLOCK 3: Divider & Feedback Content ---
        blocks.append({"type": "divider"})

        if feedback_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Feedback:*\n>{feedback_text}",  # Blockquote format
                    },
                }
            )

        # --- BLOCK 4: Links (View Convo / Open Notion) ---
        link_buttons = []
        if conversation_link:
            link_buttons.append(
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Convo 💬",
                        "emoji": True,
                    },
                    "url": conversation_link,
                    "action_id": "view_conversation",
                }
            )
        if notion_ticket_url:
            link_buttons.append(
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Notion Ticket 📝",
                        "emoji": True,
                    },
                    "url": notion_ticket_url,
                    "action_id": "open_notion",
                }
            )

        if link_buttons:
            blocks.append({"type": "actions", "elements": link_buttons})

        # --- BLOCK 5: Status Actions (The Control Panel) ---
        # Build button value payload: conversation_id|notion_page_id|user_email
        button_value = f"{conversation_id}|{notion_page_id or ''}|{user_email}"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Update Status:*",
                },
            }
        )

        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Investigating 👀",
                            "emoji": True,
                        },
                        "value": button_value,
                        "action_id": "action_investigating",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Changes Now Live 🚀",
                            "emoji": True,
                        },
                        "style": "primary",  # Green button
                        "value": button_value,
                        "action_id": "action_live",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Deferred ⏸️",
                            "emoji": True,
                        },
                        "value": button_value,
                        "action_id": "action_deferred",
                    },
                ],
            }
        )

        # --- BLOCK 6: Context (IDs) ---
        context_elements = []
        context_elements.append({"type": "mrkdwn", "text": f"ID: `{conversation_id}`"})

        if feedback_id:
            context_elements.append({"type": "mrkdwn", "text": f"Ref: `{feedback_id}`"})

        blocks.append({"type": "context", "elements": context_elements})

        # Send the message to Slack
        response = await client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=f"New feedback from {client_name}",  # Fallback text
        )

        logger.info(
            "[Slack Feedback] Successfully sent feedback notification",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
                "feedback_id": feedback_id,
            },
        )

        if hasattr(response, "data") and isinstance(response.data, dict):
            return response.data
        return {"ok": response.get("ok", True), "ts": response.get("ts")}

    except SlackApiError as e:
        logger.error(
            f"[Slack Feedback] Slack API error: {e.response['error']}",
            extra={"client_name": client_name, "error_details": e.response},
        )
        return None
    except Exception as e:
        logger.error(f"[Slack Feedback] Unexpected error: {e}")
        return None


async def update_feedback_message(
    channel_id: str,
    message_ts: str,
    status_text: str,
    client: Optional[AsyncWebClient] = None,
) -> bool:
    """Update a Slack feedback message to reflect status change."""
    try:
        if client is None:
            try:
                client = get_slack_client()
            except ValueError as e:
                logger.error(f"[Slack] Failed to get Slack client: {e}")
                return False

        # Fetch existing message
        response = await client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            limit=1,
            inclusive=True,
        )

        messages = response.get("messages")
        if not response.get("ok") or not messages:
            return False

        existing_message = messages[0]
        blocks = existing_message.get("blocks", [])

        # Clean existing status context
        blocks = [
            b
            for b in blocks
            if b.get("type") != "context" or "Status" not in str(b.get("elements", []))
        ]

        # Add new status
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*Status Update:* {status_text}"}
                ],
            }
        )

        await client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=blocks,
            text=f"Feedback update: {status_text}",
        )
        return True

    except Exception as e:
        logger.error(f"[Slack] Error updating message: {e}")
        return False


async def update_feedback_message_with_button_state(
    channel_id: str,
    message_ts: str,
    status_text: str,
    clicked_action: str,
    client: Optional[AsyncWebClient] = None,
) -> bool:
    """Update message status and disable/update buttons."""
    try:
        if client is None:
            try:
                client = get_slack_client()
            except ValueError as e:
                logger.error(f"[Slack] Failed to get Slack client: {e}")
                return False

        response = await client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            limit=1,
            inclusive=True,
        )

        messages = response.get("messages")
        if not response.get("ok") or not messages:
            return False

        existing_message = messages[0]
        blocks = existing_message.get("blocks", [])

        # Update buttons to disabled state
        for block in blocks:
            if block.get("type") == "actions":
                elements = block.get("elements", [])
                if any(
                    el.get("action_id")
                    in ["action_investigating", "action_live", "action_deferred"]
                    for el in elements
                ):
                    new_elements = []

                    # Helper to create disabled buttons
                    def make_btn(label, action):
                        btn = {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": label
                                + (" ✓" if clicked_action == action else ""),
                                "emoji": True,
                            },
                            "action_id": f"action_{action}_disabled",
                        }
                        if clicked_action == action:
                            btn["style"] = "primary"
                        return btn

                    new_elements.append(make_btn("Investigating", "investigating"))
                    new_elements.append(make_btn("Changes Now Live 🚀", "live"))
                    new_elements.append(make_btn("Deferred", "deferred"))

                    block["elements"] = new_elements

        # Update status context
        blocks = [
            b
            for b in blocks
            if b.get("type") != "context" or "Status" not in str(b.get("elements", []))
        ]

        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"*Status:* {status_text}"}],
            }
        )

        await client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=blocks,
            text=f"Feedback update: {status_text}",
        )
        return True

    except Exception as e:
        logger.error(f"[Slack] Error updating message buttons: {e}")
        return False
