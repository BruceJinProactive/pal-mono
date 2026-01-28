"""
Slack Feedback Notification Module

Provides functionality to send feedback notifications to Slack using Block Kit formatting.
"""

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from services import notion_service
from utils.log import logger

from ._client import get_slack_client, get_slack_user_id
from ._formatting import (
    build_actions_block,
    build_button,
    build_context_block,
    build_divider_block,
    build_fields_section,
    build_header_block,
    build_section_block,
)

# Channel lookup cache: {client_name: (channel_id, timestamp)}
# TTL: 5 minutes (300 seconds)
_CHANNEL_CACHE: Dict[str, Tuple[Optional[str], float]] = {}
_CHANNEL_CACHE_TTL = 300


def make_feedback_button(
    label: str, action: str, button_value: str, is_active: bool = False, emoji: str = ""
) -> Dict[str, Any]:
    """
    Create a feedback status button with optional active state styling.

    Args:
        label: Button label text
        action: Action ID suffix (e.g., "investigating", "live", "deferred")
        button_value: Button value payload (conversation_id|notion_page_id|user_email)
        is_active: Whether this button is currently active (shows checkmark + primary style)
        emoji: Optional emoji to append to label

    Returns:
        dict: Slack button block element
    """
    text = f"{label} {emoji}" + (" ✓" if is_active else "")
    style = "primary" if is_active else None
    return build_button(text, f"action_{action}", button_value, style=style)


async def get_feedback_channel_for_client(
    client_name: str, slack_client: AsyncWebClient
) -> Optional[str]:
    """
    Get the Slack channel ID for a specific client's feedback.

    Uses a 5-minute cache to reduce Slack API calls.

    Args:
        client_name: The account name from database
        slack_client: Slack API client for looking up channels

    Returns:
        Optional[str]: Channel ID if found, None otherwise
    """
    # Normalize cache key to lowercase to prevent duplicates
    cache_key = client_name.lower()

    # Check cache first
    current_time = time.time()
    if cache_key in _CHANNEL_CACHE:
        channel_id, cached_time = _CHANNEL_CACHE[cache_key]
        if current_time - cached_time < _CHANNEL_CACHE_TTL:
            logger.debug(
                f"[Slack] Using cached channel ID for client {client_name}: {channel_id}"
            )
            return channel_id

    # Generate expected channel name from normalized client name
    expected_channel_name = cache_key.replace(" ", "-")
    expected_channel_name = f"client-{expected_channel_name}"

    logger.debug(
        f"[Slack] Looking for channel: {expected_channel_name} (from client: {client_name})"
    )

    try:
        # Search for channel by name
        # Note: conversations_list returns all channels the bot is a member of
        cursor = None
        while True:
            params = {
                "types": "public_channel,private_channel",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor

            response = await slack_client.conversations_list(**params)

            if not response["ok"]:
                logger.error(
                    f"[Slack] Failed to list channels: {response.get('error')}"
                )
                return None
            # Search for matching channel name
            channels = response.get("channels", [])
            for channel in channels:
                if channel.get("name") == expected_channel_name:
                    channel_id = channel["id"]
                    logger.info(
                        f"[Slack] Found channel {expected_channel_name} with ID {channel_id}"
                    )
                    # Cache the result using normalized key
                    _CHANNEL_CACHE[cache_key] = (channel_id, current_time)
                    return channel_id

            # Check if there are more pages
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        logger.warning(
            f"[Slack] No channel found with name {expected_channel_name} for client {client_name}"
        )
        # Cache the "not found" result to avoid repeated lookups
        _CHANNEL_CACHE[cache_key] = (None, current_time)
        return None

    except Exception as e:
        logger.error(
            f"[Slack] Error looking up channel for {client_name}: {e}",
            exc_info=True,
        )
        return None


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
    Looks up the Notion 'Assigned to FDE' rollup (via the Client relation)
    and includes it in the Slack message when available.
    """
    try:
        # Get Slack client and channel
        if client is None:
            try:
                client = get_slack_client()
            except ValueError as e:
                logger.error(f"[Slack Feedback] Failed to get Slack client: {e}")
                return None

        # Determine channel ID: override > client-specific > default fallback
        if channel_override:
            channel_id = channel_override
        else:
            channel_id = await get_feedback_channel_for_client(client_name, client)

            # Fallback to default channel if client-specific channel not found
            if not channel_id:
                channel_id = "client-feedback"
                logger.warning(
                    f"[Slack Feedback] No client-specific channel found for {client_name}, "
                    f"using default fallback: {channel_id}"
                )

        # Look up "Assigned to FDE" from Notion using the client's FDE person field
        fde_name: Optional[str] = None
        fde_display_value: str = "Unassigned"

        try:
            fde_name = await notion_service.get_feedback_fde(client_name)

            if fde_name:
                # Resolve the name to a Slack ID to trigger a notification
                fde_user_id = await get_slack_user_id(fde_name, client)

                if fde_user_id:
                    # Format as Slack mention: <@U12345>
                    fde_display_value = f"<@{fde_user_id}>"
                else:
                    # Fallback to plain text if user not found in Slack
                    fde_display_value = fde_name

        except Exception as e:
            logger.error(
                f"[Slack Feedback] Failed to retrieve Assigned to FDE from Notion: {e}",
                extra={"client_name": client_name},
                exc_info=True,
            )

        # Build reaction emoji
        reaction_emoji = ""
        if reaction == "thumbs_up":
            reaction_emoji = "👍 "
        elif reaction == "thumbs_down":
            reaction_emoji = "👎 "

        # Build blocks using generic builders
        blocks = []

        # Header
        blocks.append(
            build_header_block(f"{reaction_emoji}New Feedback from {client_name}")
        )

        # Metadata fields (user, email, tags, FDE)
        field_data: List[tuple[str, str]] = []
        if user_name:
            field_data.append(("*User:*", user_name))
        if user_email:
            field_data.append(("*Email:*", user_email))
        if tags:
            tags_display = " ".join([f"`{tag}`" for tag in tags])
            field_data.append(("*Tags:*", tags_display))
        # Include FDE assignment if available (from Notion rollup)
        # Use the resolved Slack mention or fallback to plain text
        field_data.append(("*Assigned to FDE:*", fde_display_value or "Unassigned"))

        if field_data:
            blocks.append(build_fields_section(field_data))

        # Divider and feedback content
        blocks.append(build_divider_block())
        if feedback_text:
            blocks.append(build_section_block(f"*Feedback:*\n>{feedback_text}"))

        # Link buttons
        link_buttons = []
        if conversation_link:
            link_buttons.append(
                build_button(
                    "View Convo 💬", "view_conversation", "", url=conversation_link
                )
            )
        if notion_ticket_url:
            link_buttons.append(
                build_button(
                    "Notion Ticket 📝", "open_notion", "", url=notion_ticket_url
                )
            )
        if link_buttons:
            blocks.append(build_actions_block(link_buttons))

        # Status action buttons
        button_value = f"{conversation_id}|{notion_page_id or ''}|{user_email}"
        blocks.append(build_section_block("*Update Status:*"))
        blocks.append(
            build_actions_block(
                [
                    make_feedback_button(
                        "Investigating", "investigating", button_value, emoji="👀"
                    ),
                    make_feedback_button(
                        "Changes Now Live", "live", button_value, emoji="🚀"
                    ),
                    make_feedback_button(
                        "Deferred", "deferred", button_value, emoji="⏸️"
                    ),
                ]
            )
        )

        # Context (IDs)
        context_items = [f"Conversation ID: `{conversation_id}`"]
        if feedback_id:
            context_items.append(f"Feedback ID: `{feedback_id}`")
        blocks.append(build_context_block(context_items))

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

        # Normalize response payload and attach assigned_to_fde for downstream usage
        if hasattr(response, "data") and isinstance(response.data, dict):
            result: Dict[str, Any] = dict(response.data)
        else:
            result = {
                "ok": response.get("ok", True),
                "ts": response.get("ts"),
            }

        # Expose the resolved FDE on the function result
        result["assigned_to_fde"] = fde_name
        return result

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
    button_value: str,
    client: Optional[AsyncWebClient] = None,
) -> bool:
    """
    Update message status and button styling while keeping buttons clickable.

    Only one button will show as "active" (primary style + checkmark) at a time.
    Users can click different buttons to change the status.
    """
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

        # Update buttons - keep them clickable but style the active one
        for block in blocks:
            if block.get("type") == "actions":
                elements = block.get("elements", [])
                if any(
                    el.get("action_id")
                    in ["action_investigating", "action_live", "action_deferred"]
                    for el in elements
                ):
                    new_elements = [
                        make_feedback_button(
                            "Investigating",
                            "investigating",
                            button_value,
                            is_active=clicked_action == "investigating",
                            emoji="👀",
                        ),
                        make_feedback_button(
                            "Changes Now Live",
                            "live",
                            button_value,
                            is_active=clicked_action == "live",
                            emoji="🚀",
                        ),
                        make_feedback_button(
                            "Deferred",
                            "deferred",
                            button_value,
                            is_active=clicked_action == "deferred",
                            emoji="⏸️",
                        ),
                    ]
                    block["elements"] = new_elements

        # Remove old status context block and add new one
        blocks = [b for b in blocks if b.get("block_id") != "feedback_status"]

        blocks.append(
            {
                "type": "context",
                "block_id": "feedback_status",
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


async def send_self_onboarding_notification(
    account_name: str,
    account_display_name: str,
    user_email: str,
    user_name: Optional[str] = None,
    project_name: Optional[str] = None,
    project_address: Optional[str] = None,
    phone_number: Optional[str] = None,
    channel: Optional[str] = None,
    client: Optional[AsyncWebClient] = None,
) -> Optional[Dict[str, Any]]:
    """
    Send a notification when self-onboarding completes.

    Args:
        account_name: Name of the newly created account
        account_display_name: Display name of the newly created account
        user_email: Email of the user who completed onboarding
        user_name: Name of the user (optional)
        project_name: Name of the created project (optional)
        project_address: Address of the project (optional)
        phone_number: Assigned phone number (optional)
        channel: Slack channel to send notification (default: #test-channel for lat, #client-updates for prd)
        client: Optional Slack client to reuse

    Returns:
        dict: Response from Slack API or None if failed
    """
    try:
        # Determine channel based on environment if not provided
        if channel is None:
            runtime_env = os.getenv("RUNTIME_ENV", "dev")
            if runtime_env == "prd":
                channel = "#client-updates"
            else:
                # dev, lat, stg all use test-channel
                channel = "#test-channel"
        # Get Slack client
        if client is None:
            try:
                client = get_slack_client()
            except ValueError as e:
                logger.error(f"[Slack Self-Onboarding] Failed to get Slack client: {e}")
                return None

        # Build blocks using generic builders
        blocks = []

        # Header
        blocks.append(build_header_block("🎉 New Self-Onboarding Completed"))

        # Additional details if provided
        blocks.append(build_divider_block())
        detail_fields = [
            ("*Account:*", account_name),
            ("*Display Name:*", account_display_name),
        ]
        if user_name:
            detail_fields.append(("*User:*", user_name))
        detail_fields.append(("*Email:*", user_email))
        if project_name:
            detail_fields.append(("*Project Name:*", project_name))
        if project_address:
            detail_fields.append(("*Address:*", project_address))
        if phone_number:
            detail_fields.append(("*Phone Number:*", phone_number))

        blocks.append(build_fields_section(detail_fields))

        # Context - convert UTC to PST
        from datetime import datetime
        from zoneinfo import ZoneInfo

        utc_now = datetime.now(ZoneInfo("UTC"))
        pst_now = utc_now.astimezone(ZoneInfo("America/Los_Angeles"))
        pst_time_str = pst_now.strftime("%Y-%m-%d %I:%M:%S %p PST")

        blocks.append(build_context_block([f"Completed at: `{pst_time_str}`"]))

        # Action buttons
        button_value = f"{account_name}|{account_display_name}|{user_email}"
        blocks.append(
            build_actions_block(
                [
                    build_button(
                        "Accept ✓",
                        "onboarding_accept",
                        button_value,
                        style="primary",
                    ),
                    build_button(
                        "Discard ✗",
                        "onboarding_discard",
                        button_value,
                        style="danger",
                    ),
                ]
            )
        )

        # Send the message to Slack
        response = await client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=f"New self-onboarding completed for {account_name}",
        )

        logger.info(
            "[Slack Self-Onboarding] Successfully sent self-onboarding notification",
            extra={
                "account_name": account_name,
                "user_email": user_email,
                "channel": channel,
            },
        )

        if hasattr(response, "data") and isinstance(response.data, dict):
            return response.data
        return {"ok": response.get("ok", True), "ts": response.get("ts")}

    except SlackApiError as e:
        logger.error(
            f"[Slack Self-Onboarding] Slack API error: {e.response['error']}",
            extra={"account_name": account_name, "error_details": e.response},
        )
        return None
    except Exception as e:
        logger.error(
            f"[Slack Self-Onboarding] Unexpected error: {e}",
            extra={"account_name": account_name},
        )
        return None
