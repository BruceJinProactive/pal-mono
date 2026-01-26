"""
Slack Interactions Implementation

Handles Slack interactive components (button clicks, modals, etc.)
"""

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict
from urllib.parse import parse_qs

from fastapi import HTTPException, Request, status

from services import notion_service
from services.slack_service import make_feedback_button
from services.slack_service._client import get_slack_client
from utils.log import logger


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> bool:
    """
    Verify that the request came from Slack.

    Args:
        signing_secret: Slack signing secret
        timestamp: Request timestamp from X-Slack-Request-Timestamp header
        body: Raw request body bytes
        signature: Request signature from X-Slack-Signature header

    Returns:
        bool: True if signature is valid, False otherwise
    """
    # Form the basestring
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"

    # Create HMAC SHA256 hash
    my_signature = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    # Compare signatures
    return hmac.compare_digest(my_signature, signature)


async def _update_notion_status(
    notion_page_id: str,
    status: str,
    conversation_id: str,
) -> None:
    """
    Helper function to update Notion feedback status.

    Args:
        notion_page_id: The Notion page ID (can be empty string)
        status: The status to set (e.g., "Investigating", "Changes Now Live", "Out of Scope")
        conversation_id: The conversation ID for logging purposes
    """
    if notion_page_id:
        try:
            result = await notion_service.update_feedback_status(
                notion_page_id=notion_page_id,
                status=status,
            )
            if result:
                logger.info(
                    f"[Slack Interactions] Successfully updated Notion status to {status}",
                    extra={"notion_page_id": notion_page_id},
                )
            else:
                logger.warning(
                    f"[Slack Interactions] Notion status update returned False for status: {status}",
                    extra={"notion_page_id": notion_page_id, "status": status},
                )
        except Exception as e:
            logger.error(
                f"[Slack Interactions] Failed to update Notion status: {e}",
                extra={"notion_page_id": notion_page_id},
                exc_info=True,
            )
    else:
        logger.warning(
            "[Slack Interactions] Skipping Notion update - notion_page_id is empty. "
            "This usually means the Slack message was created before Notion integration was set up. "
            "Create a new feedback ticket to test the full integration.",
            extra={"conversation_id": conversation_id},
        )


async def handle_interactions(request: Request) -> Dict[str, Any]:
    """
    Handle Slack interaction payloads (button clicks) - STATELESS.

    This handler is completely stateless. All required data (conversation_id, notion_page_id,
    user_email) is embedded in the button payload during feedback creation. We do NOT query
    the SQL database to look up feedback records.

    Button Payload Format: "{conversation_id}|{notion_page_id}|{user_email}"

    Workflow:
    1. Verify Slack signature for security
    2. Parse button payload to extract: conversation_id, notion_page_id, user_email
    3. Handle action based on button clicked:
       - 'Investigating': Update Slack message + Update Notion status (NO email)
       - 'Changes Now Live': Update Slack message + Update Notion status + Send resolution email
       - 'Deferred': Update Slack message + Update Notion status to "Out of Scope" (NO email)

    Args:
        request: FastAPI Request object containing Slack interaction payload

    Returns:
        dict: Success response ({"ok": True}) - required by Slack

    Raises:
        HTTPException: If signature verification fails or payload is invalid

    Note:
        - Slack is the source of truth for feedback status
        - All updates are fire-and-forget (errors are logged but don't fail the request)
        - The SQL database is NOT queried during interactions (fire-and-forget logging only)
    """
    try:
        # Get Slack signing secret
        signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
        if not signing_secret:
            logger.error("[Slack Interactions] SLACK_SIGNING_SECRET not configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Slack signing secret not configured",
            )

        # Get request headers and body
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        body = await request.body()

        # Reject missing/invalid timestamps and replays
        if not timestamp.isdigit():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid timestamp",
            )
        if abs(time.time() - int(timestamp)) > 60 * 5:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Stale request",
            )

        # Verify signature
        if not verify_slack_signature(signing_secret, timestamp, body, signature):
            logger.warning("[Slack Interactions] Invalid signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )

        # Parse the form-encoded payload
        # Slack sends interaction payloads as application/x-www-form-urlencoded
        form_data = parse_qs(body.decode("utf-8"))
        payload_str = form_data.get("payload", [""])[0]

        if not payload_str:
            logger.error("[Slack Interactions] No payload in request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No payload found",
            )

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            logger.error(f"[Slack Interactions] Invalid JSON payload: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        # Extract action information
        action_type = payload.get("type")
        if action_type != "block_actions":
            logger.warning(
                f"[Slack Interactions] Unsupported interaction type: {action_type}"
            )
            return {"ok": True}

        actions = payload.get("actions", [])
        if not actions:
            logger.warning("[Slack Interactions] No actions in payload")
            return {"ok": True}

        action = actions[0]
        action_id = action.get("action_id")
        button_value = action.get("value", "")

        # Parse button value: conversation_id|notion_page_id|user_email
        # STATELESS: All data needed for the interaction is embedded in the button payload
        # We do NOT query the database - this makes the handler fully stateless
        parts = button_value.split("|")
        if len(parts) != 3:
            logger.error(
                "[Slack Interactions] Invalid button value format (expected: conversation_id|notion_page_id|user_email)",
                extra={"button_value": button_value},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid button value format",
            )

        conversation_id, notion_page_id, user_email = parts

        # Validate extracted values
        if not conversation_id or not user_email:
            logger.error(
                "[Slack Interactions] Missing required values in button payload",
                extra={
                    "conversation_id": conversation_id,
                    "notion_page_id": notion_page_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required payload values",
            )

        # Validate notion_page_id format (must be empty or 32-character hex string)
        if notion_page_id and (
            len(notion_page_id) != 32
            or not all(c in "0123456789abcdef" for c in notion_page_id.lower())
        ):
            logger.error(
                "[Slack Interactions] Invalid notion_page_id format (must be 32-character hex string)",
                extra={"notion_page_id": notion_page_id},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid notion_page_id format",
            )

        # Get message and channel info
        channel = payload.get("channel", {})
        channel_id = channel.get("id")
        message = payload.get("message", {})
        message_ts = message.get("ts")

        # Log warning if channel_id or message_ts is missing (graceful degradation)
        if not channel_id or not message_ts:
            logger.warning(
                "[Slack Interactions] Missing channel_id or message_ts in payload - Slack message updates will be skipped",
                extra={
                    "channel_id": channel_id,
                    "message_ts": message_ts,
                    "conversation_id": conversation_id,
                },
            )

        # Get user who clicked the button
        user = payload.get("user", {})
        user_name = user.get("name", "Unknown")

        logger.info(
            f"[Slack Interactions] Button clicked: {action_id}",
            extra={
                "action_id": action_id,
                "conversation_id": conversation_id,
                "notion_page_id": notion_page_id,
                "clicked_by": user_name,
            },
        )

        # Handle different actions (all operations are fire-and-forget)
        status_text = ""
        new_status = ""
        clicked_action_name = ""

        if action_id == "action_investigating":
            # ACTION A: 'Investigating' button clicked
            status_text = "👀 Investigating..."
            new_status = "Investigating"
            clicked_action_name = "investigating"
        elif action_id == "action_live":
            # ACTION B: 'Changes Now Live' button clicked
            status_text = "✅ Fix is Live!"
            new_status = "Changes Now Live"
            clicked_action_name = "live"
        elif action_id == "action_deferred":
            # ACTION C: 'Deferred' button clicked
            status_text = "⏸️ Out of scope"
            new_status = "Out of Scope"
            clicked_action_name = "deferred"
        else:
            logger.warning(
                f"[Slack Interactions] Unknown action: {action_id}",
                extra={"action_id": action_id},
            )
            return {"ok": True}

        # Update the message blocks with new button states
        blocks = message.get("blocks", [])

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
                            is_active=clicked_action_name == "investigating",
                            emoji="👀",
                        ),
                        make_feedback_button(
                            "Changes Now Live",
                            "live",
                            button_value,
                            is_active=clicked_action_name == "live",
                            emoji="🚀",
                        ),
                        make_feedback_button(
                            "Deferred",
                            "deferred",
                            button_value,
                            is_active=clicked_action_name == "deferred",
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

        # Update Slack message using chat.update API
        if channel_id and message_ts:
            try:
                client = get_slack_client()
                await client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=blocks,
                    text=f"Feedback update: {status_text}",
                )
            except Exception as e:
                logger.error(
                    f"[Slack Interactions] Failed to update Slack message: {e}",
                    extra={"conversation_id": conversation_id},
                    exc_info=True,
                )

        # Sync to Notion (Slack is source of truth)
        await _update_notion_status(
            notion_page_id=notion_page_id,
            status=new_status,
            conversation_id=conversation_id,
        )

        logger.info(
            f"[Slack Interactions] Feedback marked as {clicked_action_name}",
            extra={
                "conversation_id": conversation_id,
                "notion_page_id": notion_page_id,
                "action": clicked_action_name,
                "clicked_by": user_name,
            },
        )

        # Return success response (required by Slack)
        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[Slack Interactions] Error handling interaction: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing interaction",
        ) from e
