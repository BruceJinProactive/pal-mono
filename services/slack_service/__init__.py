"""
Slack Service

This service provides Slack integration for analytics reporting, including:
- Automated report generation and formatting
- Custom date range parsing
- Interactive Slack bot commands
- Professional table formatting for analytics data

The service supports daily, weekly, monthly, and custom date range reports
with engagement metrics, conversion data, and call quality analytics.
"""

from datetime import datetime

from fastapi.responses import JSONResponse, Response
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from utils.log import logger

from ._bot import _get_slack_handler
from ._client import get_slack_channel_from_env_key
from ._feedback import (
    get_feedback_channel_for_client,
    make_feedback_button,
    send_feedback_notification,
    send_self_onboarding_notification,
    update_feedback_message,
    update_feedback_message_with_button_state,
)
from ._formatting import (
    build_actions_block,
    build_button,
    build_context_block,
    build_divider_block,
    build_fields_section,
    build_header_block,
    build_section_block,
)
from ._messages import send_slack_message
from ._reports import send_report_to_slack as _send_report_to_slack

# =============================================================================
# PUBLIC API
# =============================================================================


async def handle_slack_events(request, body_bytes: bytes | None = None) -> Response:
    """
    Handle all Slack events by passing request to Slack Bolt handler.

    Args:
        request: FastAPI Request object
        body_bytes: Optional pre-read request body bytes (if body was already consumed)

    Returns:
        FastAPI Response object from Slack Bolt handler
    """
    try:
        # Get Slack handler
        handler = _get_slack_handler()
        if not handler:
            logger.error("[Slackbot] Slack handler not configured")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "message": "Slack handler not configured"},
            )

        # If body was already read, reconstruct the request
        if body_bytes is not None:

            async def receive():
                return {"type": "http.request", "body": body_bytes}

            # Reconstruct request with the pre-read body
            from fastapi import Request

            reconstructed_request = Request(scope=request.scope, receive=receive)
            return await handler.handle(reconstructed_request)
        else:
            # Body not consumed yet, pass original request
            return await handler.handle(request)

    except Exception as e:
        logger.error(f"[Slackbot] Error handling Slack event: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e)}
        )


async def send_report_to_slack(
    slack_channel: str | None = None,
    client: AsyncWebClient | None = None,
    session: Session | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    account_name: str | None = None,
    show_time: bool = False,
    timezone_id: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    """
    Send report to Slack with conversion analytics.

    Args:
        slack_channel (str): Slack channel to send to (optional, uses env variable if not provided)
        client: Optional Slack client to reuse
        session (Session): Database session
        start_date (datetime | None): Start date for the calculation (in UTC)
        end_date (datetime | None): End date for the calculation (in UTC)
        account_name (str | None): Optional account name to filter by
        show_time (bool): If True, show full datetime with time and timezone in report title
        timezone_id (str | None): Timezone ID to convert UTC times to local time
        timezone_name (str | None): Timezone abbreviation to display

    Returns:
        dict: Status of the operation
    """
    return await _send_report_to_slack(
        slack_channel,
        client,
        session,
        start_date,
        end_date,
        account_name,
        show_time,
        timezone_id,
        timezone_name,
    )


# Export public functions
__all__ = [
    "handle_slack_events",
    "send_report_to_slack",
    "send_slack_message",
    "send_feedback_notification",
    "send_self_onboarding_notification",
    "update_feedback_message",
    "update_feedback_message_with_button_state",
    "get_feedback_channel_for_client",
    "make_feedback_button",
    "build_header_block",
    "build_section_block",
    "build_fields_section",
    "build_divider_block",
    "build_context_block",
    "build_button",
    "build_actions_block",
    "get_slack_channel_from_env_key",
]
