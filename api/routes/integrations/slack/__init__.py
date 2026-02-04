"""
Slack Integration Routes

Handles Slack interactive components (button clicks, etc.)
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse

from utils.log import logger

from . import _interactions

slack_router = APIRouter(prefix="/slack", tags=["Slack Integration"])


@slack_router.post("/events", status_code=http_status.HTTP_200_OK)
async def slack_events(request: Request):
    """
    Handle Slack events (app mentions, direct messages, etc.).

    This endpoint receives Slack event payloads when:
    - Someone @mentions the bot
    - Someone sends a DM to the bot
    - Other subscribed events occur

    Slack sends a URL verification challenge when you first configure this endpoint.
    The endpoint must respond with the challenge value to complete verification.

    Returns:
        Response: FastAPI Response object from Slack Bolt handler
    """
    import json

    from services import slack_service

    # Read the body once (can only be read once per request)
    body_bytes = await request.body()

    try:
        # Parse JSON to check for URL verification challenge
        data = json.loads(body_bytes.decode("utf-8"))

        # Handle URL verification challenge directly
        if data.get("type") == "url_verification":
            challenge = data.get("challenge")
            if challenge:
                logger.info(
                    f"[Slack Events] URL verification challenge received: {challenge}"
                )
                return {"challenge": challenge}

    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"[Slack Events] Could not parse request body as JSON: {e}")
        # Continue to let Slack Bolt handler process it

    # For other events, pass body bytes to the service handler
    return await slack_service.handle_slack_events(request, body_bytes)


@slack_router.get("/interactions", status_code=http_status.HTTP_200_OK)
async def slack_interactions_verify(_request: Request):
    """
    Handle Slack URL verification for Interactivity endpoint.

    When you save the Request URL in Slack app settings, Slack sends
    a GET request to verify the endpoint is accessible.
    """
    logger.info("[Slack] GET request received for interactions endpoint verification")
    return JSONResponse(
        status_code=http_status.HTTP_200_OK,
        content={"status": "ok", "message": "Slack interactions endpoint is ready"},
    )


@slack_router.post("/interactions", status_code=http_status.HTTP_200_OK)
async def slack_interactions(request: Request):
    """
    Handle Slack interactive components (button clicks).

    This endpoint receives Slack interaction payloads when users click
    buttons in Slack messages (e.g., feedback status buttons).

    The payload contains:
    - action_id: The action that was triggered (e.g., "action_investigating", "action_live")
    - value: The button value (format: "conversation_id|notion_page_id|user_email")
    - channel: The Slack channel
    - message: The original message
    - user: The Slack user who clicked

    Returns:
        dict: Success response

    Note:
        - Verifies Slack signature for security
        - Updates Slack message to reflect status change
        - Syncs status to Notion (Slack is source of truth)
        - Sends resolution email when "Changes Now Live" is clicked
    """
    return await _interactions.handle_interactions(request)
