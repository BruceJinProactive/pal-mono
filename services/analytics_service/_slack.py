import threading
from datetime import datetime

from fastapi.responses import JSONResponse, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.ext.asyncio import AsyncSession

import db
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


async def send_daily_report_to_slack(
    channel: str | None = None,
    client: AsyncWebClient | None = None,
    session: AsyncSession | None = None,
) -> dict:
    """
    Send a comprehensive daily commerce report to Slack with conversion analytics.

    Args:
        channel (str): Slack channel to send to (optional, uses secret manager if not provided)
        client (AsyncWebClient): Optional async Slack client to reuse (creates new one if not provided)
        session (Session): Database session for fetching conversion data

    Returns:
        dict: Status of the operation
    """
    try:
        # Get bot token from AWS Secrets Manager with environment variable fallback
        try:
            bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
        except ValueError as e:
            logger.error(
                f"[Slackbot] SLACK_BOT_TOKEN not found in secrets manager or environment: {e}"
            )
            return {"status": "error", "message": "Slack bot token not configured"}

        # Get channel from parameter or AWS Secrets Manager
        if not channel:
            try:
                target_channel = get_client_secret_with_fallback("SLACK_CHANNEL")
            except ValueError:
                target_channel = "#test-channel"  # Default fallback
        else:
            target_channel = channel

        # Use provided client or create new one
        if client is None:
            client = AsyncWebClient(token=bot_token)

        # Get conversion data for the report
        conversion_data = []
        try:
            import asyncio

            from db.session import SyncSessionLocal
            from services import analytics_service

            def _get_conversion_data_sync():
                with SyncSessionLocal() as sync_session:
                    return analytics_service.get_conversion_data(sync_session)

            conversion_data = await asyncio.to_thread(_get_conversion_data_sync)
            logger.info(
                f"[Slackbot] Retrieved {len(conversion_data)} conversion records"
            )
        except Exception as e:
            logger.warning(f"[Slackbot] Could not fetch conversion data: {e}")

        # Build Slack blocks
        if conversion_data:
            from ._utils import build_slack_report_blocks

            blocks = build_slack_report_blocks(conversion_data)

            # Send rich report with blocks
            response = await client.chat_postMessage(
                channel=target_channel,
                text="📊 Palona Daily Commerce Report",  # Fallback text
                blocks=blocks,
            )
        else:
            # Fallback to simple message if no data
            current_date = datetime.now().strftime("%B %d, %Y")
            fallback_text = f"📊 *Palona Daily Report*\n\nGenerated on: {current_date}\n\n⚠️ No conversion data available at this time."

            response = await client.chat_postMessage(
                channel=target_channel, text=fallback_text, mrkdwn=True
            )

        if response["ok"]:
            logger.info(
                f"[Slackbot] Daily report sent successfully to Slack channel {target_channel}"
            )
            return {
                "status": "success",
                "message": f"Daily report sent to Slack channel {target_channel} successfully",
            }
        else:
            logger.error(
                f"[Slackbot] Failed to send to Slack: {response.get('error', 'Unknown error')}"
            )
            return {
                "status": "error",
                "message": f"Failed to send to Slack: {response.get('error', 'Unknown error')}",
            }

    except SlackApiError as e:
        logger.error(f"[Slackbot] Slack API error: {e.response['error']}")
        return {"status": "error", "message": f"Slack API error: {e.response['error']}"}
    except Exception as e:
        logger.error(f"[Slackbot] Error sending daily report to Slack: {e}")
        return {"status": "error", "message": f"Failed to send report: {str(e)}"}


def create_slack_app():
    """Create and configure Slack Bolt app with event handlers."""
    try:
        # Get bot token and signing secret from AWS Secrets Manager with environment variable fallback
        bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
        signing_secret = get_client_secret_with_fallback("SLACK_SIGNING_SECRET")
    except ValueError as e:
        logger.warning(
            f"[Slackbot] SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET not found in secrets manager or environment: {e} - Slack event handling disabled"
        )
        return None

    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    @app.message("daily")
    async def handle_daily_request(message, say, client):
        """Handle when users send 'daily' in the channel."""
        try:
            channel = message["channel"]
            user = message["user"]

            logger.info(
                f"[Slackbot] User {user} requested daily report in channel {channel}"
            )

            # Get async database session for conversion data using proper context handling
            result = {"status": "error", "message": "No result"}
            async for session in db.get_db_async():
                # Send the daily report using the provided client and session
                result = await send_daily_report_to_slack(channel, client, session)

            if result["status"] == "success":
                logger.info(f"[Slackbot] Daily report sent successfully to {channel}")
            else:
                logger.error(
                    f"[Slackbot] Failed to send daily report: {result['message']}"
                )

        except Exception as e:
            logger.error(f"[Slackbot] Error handling daily request: {e}")

    return app


# Global Slack app instance and thread safety
_slack_app = None
_slack_handler = None
_slack_init_lock = threading.Lock()


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
        handler = _get_slack_handler()
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


def _get_slack_handler():
    """Internal function to get the Slack request handler."""
    global _slack_app, _slack_handler

    if _slack_handler is None:
        with _slack_init_lock:
            # Double-check pattern to prevent race conditions
            if _slack_handler is None:
                _slack_app = create_slack_app()
                if _slack_app:
                    _slack_handler = AsyncSlackRequestHandler(_slack_app)

    return _slack_handler
