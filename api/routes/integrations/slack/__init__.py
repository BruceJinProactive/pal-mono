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
