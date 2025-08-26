import asyncio
import os
import threading
import uuid
from datetime import datetime

from mixpanel import Mixpanel
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

import db
from api.schemas.admin.analytics import AnalyticsReportType
from api.schemas.admin.analytics import Event as AnalyticsEvent
from api.schemas.admin.analytics import GetAllReportsResponse, PerformanceReport
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from ._utils import handle_analytics_date_range, process_analytics_results_to_dict

# BRUCETODO: DELETE - Mixpanel related variables
MIXPANEL_BASE_URL = "https://mixpanel.com/api"
MIXPANEL_PROJECT_ID = 3584752
MIXPANEL_WORKSPACE_ID = 9701744
BOOKMARK_ID_MAPPING = {
    "ORDER": 81979859,
}
MIXPANEL_REPORTS = [
    (81979859, "Total Order Value"),
]


def get_analytics_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> GetAllReportsResponse:
    """
    Get DAU, Message Turns, Order Total, and Order Numbers analytics data for a given account within a date range.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation. If None, defaults to 7 days ago
        end_date (datetime | None): End date for the calculation. If None, defaults to today

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    try:
        # Handle date range validation and defaults
        start_date, end_date = handle_analytics_date_range(start_date, end_date)
        message_repo = db.MessageRepository(session)
        order_repo = db.OrderRepository(session)

        # Fetch and process DAU data
        dau_result = message_repo.get_daily_active_users(
            account_id, start_date, end_date
        )
        dau_data = process_analytics_results_to_dict(
            dau_result, start_date, end_date, AnalyticsReportType.DAU
        )

        # Fetch and process Message Turns data
        message_turns_result = message_repo.get_daily_message_turns(
            account_id, start_date, end_date
        )
        message_turns_data = process_analytics_results_to_dict(
            message_turns_result,
            start_date,
            end_date,
            AnalyticsReportType.MESSAGE_TURNS,
        )
        # Fetch order data (contains both value and count)
        order_result = order_repo.get_order_value(account_id, start_date, end_date)

        # Process Order Total data (uses DB column key via report_name)
        order_value_data = process_analytics_results_to_dict(
            order_result,
            start_date,
            end_date,
            AnalyticsReportType.ORDER_TOTAL,
        )
        logger.info(
            f"Analytics: Processed Message Turns data for account {AnalyticsReportType.ORDER_TOTAL} from {order_value_data}"
        )

        # Create and return reports
        reports = [
            PerformanceReport(name=AnalyticsReportType.DAU, data=dau_data),
            PerformanceReport(
                name=AnalyticsReportType.MESSAGE_TURNS, data=message_turns_data
            ),
            PerformanceReport(
                name=AnalyticsReportType.ORDER_TOTAL, data=order_value_data
            ),
        ]

        return GetAllReportsResponse(reports=reports)

    except ValueError as e:
        logger.error(f"Analytics: Date validation error for account {account_id}: {e}")
        return GetAllReportsResponse(reports=[])
    except Exception as e:
        logger.error(
            f"Analytics: Error calculating analytics for account {account_id}: {e}"
        )
        logger.exception("Analytics: Full analytics exception traceback:")
        return GetAllReportsResponse(reports=[])


# BRUCETODO: DELETE - Mixpanel related variables
def track_event(user_id: str, event_name: AnalyticsEvent, event_properties: dict):
    def _track():
        try:
            MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
            mp = None
            if MIXPANEL_PROJECT_TOKEN:
                mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)
            if mp:
                runtime_env = os.getenv("RUNTIME_ENV", "dev")
                event_properties["runtime_env"] = runtime_env
                mp.track(user_id, event_name, event_properties)
        except Exception as e:
            logger.error(
                f"Analytics: Error tracking event {event_name} for user {user_id}: {e}"
            )

    asyncio.create_task(asyncio.to_thread(_track))


async def send_daily_report_to_slack(
    channel: str | None = None, client: AsyncWebClient | None = None
) -> dict:
    """
    Send a simple daily report message to Slack via bot.

    Args:
        channel (str): Slack channel to send to (optional, uses secret manager if not provided)
        client (AsyncWebClient): Optional async Slack client to reuse (creates new one if not provided)

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

        # Create the message
        current_date = datetime.now().strftime("%B %d, %Y")
        message_text = f"📊 *Palona Daily Report*\n\nGenerated on: {current_date}\n\nReport content will be added here in future updates."

        # Send message to Slack
        response = await client.chat_postMessage(
            channel=target_channel, text=message_text, mrkdwn=True
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


# Initialize Slack Bolt app
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

            # Send the daily report using the provided client
            result = await send_daily_report_to_slack(channel, client)

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


async def handle_slack_events(request):
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
            return {"status": "error", "message": "Slack handler not configured"}

    except Exception as e:
        logger.error(f"[Slackbot] Error handling Slack event: {e}")
        return {"status": "error", "message": str(e)}


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
