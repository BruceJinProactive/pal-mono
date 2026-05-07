"""
Slack Interactions Implementation

Handles Slack interactive components (button clicks, modals, etc.)
"""

import asyncio
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict
from urllib.parse import parse_qs

from fastapi import HTTPException, Request, status
from fastapi.responses import Response

from services import notion_service, postmark_service
from services.slack_service import make_feedback_button
from services.slack_service._client import get_slack_client
from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Track background tasks so they aren't garbage-collected before completion.
_background_tasks: set[asyncio.Task[Any]] = set()


def _schedule_background_task(
    coro: Any,
    name: str,
) -> None:
    """Schedule an async coroutine as a background task with exception logging."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _done(t: asyncio.Task[Any]) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.exception(
                "[Slack Interactions] Background task failed: %s",
                exc,
                extra={"task_name": t.get_name()},
            )

    task.add_done_callback(_done)


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
    conversation_id: str = "",
    feedback_id: str = "",
) -> None:
    """
    Helper function to update Notion feedback status.

    Args:
        notion_page_id: The Notion page ID (can be empty string)
        status: The status to set (e.g., "Investigating", "Changes Now Live", "Out of Scope")
        conversation_id: The conversation ID for logging purposes (optional)
        feedback_id: The feedback ID for logging purposes (optional)
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
            extra={"feedback_id": feedback_id, "conversation_id": conversation_id},
        )


async def _handle_onboarding_accept(
    button_value: str,
    channel_id: str,
    message_ts: str,
    message: Dict[str, Any],
    clicked_by: str,
) -> Dict[str, Any]:
    """
    Handle 'Accept' button click for self-onboarding notifications.

    Updates the Slack message to show accepted status.

    Args:
        button_value: Format "account_name|account_display_name|user_email"
        channel_id: Slack channel ID
        message_ts: Slack message timestamp
        message: Original Slack message
        clicked_by: Slack username of person who clicked the button

    Returns:
        dict: Success response for Slack
    """
    # Parse button value
    parts = button_value.split("|")
    if len(parts) != 3:
        logger.error(
            f"[Slack Interactions] Invalid onboarding button value format: {button_value}"
        )
        return {"ok": True}

    account_name, account_display_name, user_email = parts

    logger.info(
        "[Slack Interactions] Onboarding 'Accept' clicked",
        extra={
            "account_name": account_name,
            "account_display_name": account_display_name,
            "user_email": user_email,
            "clicked_by": clicked_by,
        },
    )

    # Create Notion client page
    notion_url = None
    try:
        notion_url = await notion_service.create_client_page(
            account_name=account_name,
            account_display_name=account_display_name,
        )
    except Exception as e:
        logger.error(
            f"[Slack Interactions] Failed to create Notion client page: {e}",
            extra={"account_name": account_name},
            exc_info=True,
        )

    # Build status message
    if notion_url:
        status_text = f"✅ {account_name} has been accepted by @{clicked_by} - <{notion_url}|View in Notion>"
    else:
        status_text = f"✅ {account_name} has been accepted by @{clicked_by} (Notion page creation failed)"

    # Update Slack message - remove buttons and add status
    blocks = message.get("blocks", [])
    blocks = [b for b in blocks if b.get("type") != "actions"]
    blocks.append(
        {
            "type": "context",
            "block_id": "onboarding_status",
            "elements": [{"type": "mrkdwn", "text": status_text}],
        }
    )

    # Update Slack message
    try:
        client = get_slack_client()
        await client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=blocks,
            text=f"Onboarding accepted: {account_name}",
        )
    except Exception as e:
        logger.error(
            f"[Slack Interactions] Failed to update Slack message: {e}",
            extra={"account_name": account_name},
            exc_info=True,
        )

    return {"ok": True}


async def _handle_onboarding_discard(
    button_value: str,
    channel_id: str,
    message_ts: str,
    message: Dict[str, Any],
    clicked_by: str,
) -> Dict[str, Any]:
    """
    Handle 'Discard' button click for self-onboarding notifications.

    Updates the Slack message to show discarded status.

    Args:
        button_value: Format "account_name|account_display_name|user_email"
        channel_id: Slack channel ID
        message_ts: Slack message timestamp
        message: Original Slack message
        clicked_by: Slack username of person who clicked the button

    Returns:
        dict: Success response for Slack
    """
    # Parse button value
    parts = button_value.split("|")
    if len(parts) != 3:
        logger.error(
            f"[Slack Interactions] Invalid onboarding button value format: {button_value}"
        )
        return {"ok": True}

    account_name, account_display_name, user_email = parts

    logger.info(
        "[Slack Interactions] Onboarding 'Discard' clicked",
        extra={
            "account_name": account_name,
            "account_display_name": account_display_name,
            "user_email": user_email,
            "clicked_by": clicked_by,
        },
    )

    # Update Slack message - remove buttons and add status
    blocks = message.get("blocks", [])
    blocks = [b for b in blocks if b.get("type") != "actions"]
    blocks.append(
        {
            "type": "context",
            "block_id": "onboarding_status",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"❌ {account_name} has been discarded by @{clicked_by}",
                }
            ],
        }
    )

    # Update Slack message
    try:
        client = get_slack_client()
        await client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=blocks,
            text=f"Onboarding discarded: {account_name}",
        )
    except Exception as e:
        logger.error(
            f"[Slack Interactions] Failed to update Slack message: {e}",
            extra={"account_name": account_name},
            exc_info=True,
        )

    return {"ok": True}


async def handle_interactions(request: Request) -> Dict[str, Any] | Response:
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
       - 'Investigating': Update Slack message + Update Notion status + Send feedback receipt email
       - 'Changes Now Live': Update Slack message + Update Notion status + Send resolution email
       - 'Deferred': Update Slack message + Update Notion status to "Out of Scope" + Send backlog email

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
        # Get Slack signing secret from AWS Secrets Manager or environment
        try:
            signing_secret = get_server_secret_with_fallback("SLACK_SIGNING_SECRET")
        except ValueError as e:
            logger.error(
                f"[Slack Interactions] SLACK_SIGNING_SECRET not configured: {e}"
            )
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

        # Handle modal form submissions (Mercury interactive workflows)
        if action_type == "view_submission":
            callback_id = payload.get("view", {}).get("callback_id", "")
            if callback_id.startswith("mercury_"):
                from ._mercury_actions import handle_mercury_view_submission

                _schedule_background_task(
                    handle_mercury_view_submission(payload),
                    name=f"mercury_view:{callback_id}",
                )
                # Slack requires an empty 200 response to close the modal.
                # Returning JSON (e.g. {"ok": True}) causes "trouble connecting" error.
                return Response(status_code=200)
            logger.warning(
                f"[Slack Interactions] Unhandled view_submission: {callback_id}"
            )
            return Response(status_code=200)

        # Handle external_select typeahead suggestions
        if action_type == "block_suggestion":
            action_id = payload.get("action_id", "")
            query = payload.get("value", "")
            if action_id == "account_name_value":
                from ._mercury_actions import handle_mercury_company_search

                options = await handle_mercury_company_search(query)
                return {"options": options}
            return {"options": []}

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

        # Handle dispatch_action from Create Client modal dropdown
        if action_id == "account_name_value":
            container = payload.get("container", {})
            if container.get("type") == "view":
                from ._mercury_actions import handle_mercury_account_selected

                await handle_mercury_account_selected(payload, action)
                return {"ok": True}

        # Handle Mercury help menu button clicks
        if action_id and action_id.startswith("mercury_"):
            from ._mercury_actions import (
                MERCURY_DIRECT_ACTIONS,
                handle_mercury_block_action,
            )

            if action_id in MERCURY_DIRECT_ACTIONS:
                # Direct commands don't open modals — safe to background.
                _schedule_background_task(
                    handle_mercury_block_action(payload, action),
                    name=f"mercury_action:{action_id}",
                )
            else:
                # Modal openers use trigger_id which expires in 3 s — must await.
                await handle_mercury_block_action(payload, action)
            return {"ok": True}
        button_value = action.get("value", "")

        # Get message and channel info (needed for all actions)
        channel = payload.get("channel", {})
        channel_id = channel.get("id")
        message = payload.get("message", {})
        message_ts = message.get("ts")

        # Get user who clicked the button
        user = payload.get("user", {})
        slack_user_name = user.get("name", "Unknown")

        # Handle onboarding actions first (different button value format)
        if action_id in ["onboarding_accept", "onboarding_discard"]:
            if action_id == "onboarding_accept":
                return await _handle_onboarding_accept(
                    button_value=button_value,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    message=message,
                    clicked_by=slack_user_name,
                )
            else:  # onboarding_discard
                return await _handle_onboarding_discard(
                    button_value=button_value,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    message=message,
                    clicked_by=slack_user_name,
                )

        # Parse button value for feedback actions
        # STATELESS: All data needed for the interaction is embedded in the button payload
        # We do NOT query the database - this makes the handler fully stateless
        #
        # New format (JSON): {"feedback_id": "...", "notion_page_id": "...", "user_email": "...", "user_name": "...", "feedback_text": "...", "tags": [...]}
        # Legacy format (JSON): {"conversation_id": "...", "notion_page_id": "...", "user_email": "..."}
        # Legacy format (pipe-delimited): conversation_id|notion_page_id|user_email
        feedback_id = ""
        conversation_id = ""
        notion_page_id = ""
        user_email = ""
        user_name = ""
        feedback_text = ""
        tags: list[str] = []

        # Try parsing as JSON first (new format)
        try:
            payload_data = json.loads(button_value)
            feedback_id = payload_data.get("feedback_id", "")
            # For backward compatibility, check for conversation_id if feedback_id is not present
            if not feedback_id:
                conversation_id = payload_data.get("conversation_id", "")
            notion_page_id = payload_data.get("notion_page_id", "")
            user_email = payload_data.get("user_email", "")
            user_name = payload_data.get("user_name", "")
            feedback_text = payload_data.get("feedback_text", "")
            tags = payload_data.get("tags", [])
        except json.JSONDecodeError as e:
            # Fall back to legacy pipe-delimited format for backward compatibility
            parts = button_value.split("|")
            if len(parts) != 3:
                logger.error(
                    "[Slack Interactions] Invalid button value format (expected JSON or pipe-delimited)",
                    extra={"button_value": button_value},
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid button value format",
                ) from e
            conversation_id, notion_page_id, user_email = parts

        # Validate extracted values
        if not feedback_id and not conversation_id:
            logger.error(
                "[Slack Interactions] Missing required values in button payload (need feedback_id or conversation_id)",
                extra={
                    "feedback_id": feedback_id,
                    "conversation_id": conversation_id,
                    "notion_page_id": notion_page_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required payload values",
            )

        if not user_email:
            logger.error(
                "[Slack Interactions] Missing user_email in button payload",
                extra={
                    "feedback_id": feedback_id,
                    "conversation_id": conversation_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing user_email in payload",
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

        logger.info(
            f"[Slack Interactions] Button clicked: {action_id}",
            extra={
                "action_id": action_id,
                "feedback_id": feedback_id,
                "conversation_id": conversation_id,
                "notion_page_id": notion_page_id,
                "clicked_by": slack_user_name,
            },
        )

        # Handle different actions (all operations are fire-and-forget)
        status_text = ""
        new_status = ""
        clicked_action_name = ""

        if action_id == "action_investigating":
            # ACTION A: 'Investigating' button clicked
            status_text = "👀 Looking into it..."
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
            feedback_id=feedback_id,
        )

        # Send feedback receipt email (only for 'Investigating' action)
        if clicked_action_name == "investigating" and user_email:
            try:
                email_sent = await postmark_service.send_feedback_receipt(
                    user_email=user_email,
                    user_name=user_name or user_email,
                    feedback_text=feedback_text,
                )
                if email_sent:
                    logger.info(
                        "[Slack Interactions] Sent feedback receipt email to user",
                        extra={
                            "feedback_id": feedback_id,
                            "conversation_id": conversation_id,
                            "user_email": user_email,
                        },
                    )
                else:
                    logger.warning(
                        "[Slack Interactions] Feedback receipt email not sent",
                        extra={
                            "feedback_id": feedback_id,
                            "conversation_id": conversation_id,
                            "user_email": user_email,
                        },
                    )
            except Exception as e:
                logger.error(
                    f"[Slack Interactions] Error sending feedback receipt email: {e}",
                    extra={
                        "feedback_id": feedback_id,
                        "conversation_id": conversation_id,
                        "user_email": user_email,
                    },
                    exc_info=True,
                )

        # Construct conversation link (used by resolution and backlog emails)
        console_base_url = os.getenv(
            "PAL_CONSOLE_BASE_URL", "https://console.palona.ai"
        )
        # Use feedbackId if available, otherwise fall back to conversationId for legacy support
        if feedback_id:
            conversation_link = (
                f"{console_base_url}/hosting/conversations?feedbackId={feedback_id}"
            )
        else:
            conversation_link = f"{console_base_url}/hosting/conversations?conversationId={conversation_id}&tab=feedback"

        # Send resolution notice email (only for 'Changes Now Live' action)
        if clicked_action_name == "live" and user_email:
            try:
                email_sent = await postmark_service.send_resolution_notice(
                    user_email=user_email,
                    user_name=user_name or user_email,
                    tags=tags,
                    feedback_content=feedback_text,
                    action_url=conversation_link,
                )
                if email_sent:
                    logger.info(
                        "[Slack Interactions] Sent resolution notice email to user",
                        extra={
                            "feedback_id": feedback_id,
                            "conversation_id": conversation_id,
                            "user_email": user_email,
                        },
                    )
                else:
                    logger.warning(
                        "[Slack Interactions] Resolution notice email not sent",
                        extra={
                            "feedback_id": feedback_id,
                            "conversation_id": conversation_id,
                            "user_email": user_email,
                        },
                    )
            except Exception as e:
                logger.error(
                    f"[Slack Interactions] Error sending resolution notice email: {e}",
                    extra={
                        "feedback_id": feedback_id,
                        "conversation_id": conversation_id,
                        "user_email": user_email,
                    },
                    exc_info=True,
                )

        # Send feedback backlog email (only for 'Deferred' action)
        if clicked_action_name == "deferred" and user_email:
            try:
                email_sent = await postmark_service.send_feedback_backlog(
                    user_email=user_email,
                    user_name=user_name or user_email,
                    feedback_text=feedback_text,
                    conversation_url=conversation_link,
                )
                if email_sent:
                    logger.info(
                        "[Slack Interactions] Sent feedback backlog email to user",
                        extra={
                            "feedback_id": feedback_id,
                            "conversation_id": conversation_id,
                            "user_email": user_email,
                        },
                    )
                else:
                    logger.warning(
                        "[Slack Interactions] Feedback backlog email not sent",
                        extra={
                            "feedback_id": feedback_id,
                            "conversation_id": conversation_id,
                            "user_email": user_email,
                        },
                    )
            except Exception as e:
                logger.error(
                    f"[Slack Interactions] Error sending feedback backlog email: {e}",
                    extra={
                        "feedback_id": feedback_id,
                        "conversation_id": conversation_id,
                        "user_email": user_email,
                    },
                    exc_info=True,
                )

        logger.info(
            f"[Slack Interactions] Feedback marked as {clicked_action_name}",
            extra={
                "feedback_id": feedback_id,
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
