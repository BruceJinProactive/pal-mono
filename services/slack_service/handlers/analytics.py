"""
Analytics Command Handler

This module handles all analytics-related Slack commands including:
- Report requests (daily, weekly, monthly, custom date ranges)
- Last X hours reports
- Account filtering and channel verification
- Report generation and sending

Coordinates between:
- formatters.analytics for data formatting
- utils.channel for authorization
- services.analytics_service for data fetching
"""

from datetime import datetime

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from db.session import SyncSessionLocal
from services.analytics_service._implementation import get_reports
from utils.log import logger

# Import from our new modules
from .._client import get_slack_credentials
from ..formatters.analytics import (
    format_unified_report_for_slack,
    get_account_timezone,
    get_date_range_for_hours,
    get_date_range_for_period,
    parse_custom_date_range,
    parse_last_hours,
)
from ..utils.channel import determine_account_filter, get_channel_name
from ..utils.message_parser import parse_account_name_from_message


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
    thread_ts: str | None = None,
) -> dict:
    """
    Send a comprehensive analytics report to Slack.

    Args:
        slack_channel: Slack channel to send to (optional, uses secret manager if not provided)
        client: Optional async Slack client to reuse (creates new one if not provided)
        session: Database session for fetching analytics data
        start_date: Start date for the report (in UTC)
        end_date: End date for the report (in UTC)
        account_name: Optional account name to filter by (from message like "daily for acme")
        show_time: If True, show full datetime with time and timezone in report title
        timezone_id: Timezone ID to convert UTC times to local time (e.g., 'America/New_York')
        timezone_name: Timezone abbreviation to display (e.g., 'EST', 'PST')
        thread_ts: Optional thread timestamp to reply in thread

    Returns:
        dict: Status of the operation
    """
    try:
        # Validate required session
        if session is None:
            return {"status": "error", "message": "Database session not available"}

        # Get Slack credentials
        try:
            bot_token, default_channel = get_slack_credentials()
            target_channel = slack_channel or default_channel
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        # Create client if not provided
        if client is None:
            client = AsyncWebClient(token=bot_token)

        # At this point, client is guaranteed to be non-None
        assert client is not None  # Type hint for static analysis

        # Get human-readable channel name for logging
        channel_display_name = await get_channel_name(client, target_channel)

        # Determine account filtering based on channel and message
        account_id_filter, error_message = determine_account_filter(
            target_channel, session, account_name, channel_display_name
        )

        # Check for validation errors
        if error_message:
            logger.warning(f"[Slackbot] Account validation failed: {error_message}")
            return {"status": "error", "message": error_message}

        # Fetch analytics reports
        # For single account reports, group by project_id to show project-level breakdown
        # For multi-account reports, group by account_id to show account-level breakdown
        group_by_fields = ["project_id"] if account_id_filter else ["account_id"]

        logger.info(
            f"[Slackbot] Fetching analytics reports from {start_date} to {end_date} "
            f"for channel '{channel_display_name}' (account_id: {account_id_filter}, group_by: {group_by_fields})"
        )
        reports = await get_reports(
            session, account_id_filter, start_date, end_date, group_by=group_by_fields
        )
        if not reports.reports:
            logger.warning("[Slackbot] No reports data returned from analytics service")
            return {"status": "error", "message": "No reports data available"}

        # Generate Slack blocks
        logger.info(
            f"[Slackbot] Converting {len(reports.reports)} reports to Slack blocks"
        )
        message_blocks = format_unified_report_for_slack(
            reports.reports,
            None,
            start_date,
            end_date,
            show_time=show_time,
            timezone_id=timezone_id,
            timezone_name=timezone_name,
            account_id_filter=account_id_filter,
            account_name=account_name,
            session=session,
        )
        if not message_blocks or "blocks" not in message_blocks:
            logger.error("[Slackbot] Failed to generate valid Slack blocks structure")
            return {"status": "error", "message": "Failed to generate Slack blocks"}

        logger.info(
            f"[Slackbot] Successfully converted {len(reports.reports)} reports to Slack blocks"
        )

        # Send to Slack
        logger.info(f"[Slackbot] Sending report to Slack channel: {target_channel}")
        post_params = {
            "channel": target_channel,
            "text": "Analytics Report",
            **message_blocks,
        }
        if thread_ts:
            post_params["thread_ts"] = thread_ts
        response = await client.chat_postMessage(**post_params)

        if response["ok"]:
            logger.info(f"[Slackbot] Report sent successfully to {target_channel}")
            return {
                "status": "success",
                "message": f"Report sent to {target_channel} successfully",
            }
        else:
            error_msg = response.get("error", "Unknown error")
            logger.error(f"[Slackbot] Slack API error: {error_msg}")
            return {
                "status": "error",
                "message": f"Failed to send to Slack: {error_msg}",
            }

    except SlackApiError as e:
        error_msg = f"Slack API error: {e.response['error']}"
        logger.error(f"[Slackbot] {error_msg}")
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Failed to send report: {str(e)}"
        logger.error(f"[Slackbot] {error_msg}")
        return {"status": "error", "message": error_msg}


async def handle_report_request(
    period: str, message, client, custom_dates: tuple[datetime, datetime] | None = None
):
    """
    Generic handler for all report requests (daily, weekly, monthly, custom).

    Supports account filtering via message syntax:
    - "daily" - shows all accounts (if in internal channel) or restricted
    - "daily for acme-restaurant" - shows only acme-restaurant account
    - "weekly for burger-place" - shows only burger-place account

    Args:
        period: The report period ("daily", "weekly", "monthly", "custom")
        message: Slack message object
        client: Slack client object
        custom_dates: Optional tuple of (start_date, end_date) for custom ranges
    """
    try:
        slack_channel = message.get("channel")
        user = message["user"]
        message_text = message.get("text", "")

        # Get human-readable channel name for logging
        channel_name = await get_channel_name(client, slack_channel)

        # Parse account name from message if provided
        account_name = parse_account_name_from_message(message_text)

        logger.info(
            f"[Slackbot] User {user} requested {period} report in channel {channel_name}"
            + (f" for account '{account_name}'" if account_name else "")
        )

        # Get database session for conversion data using proper context handling
        session = SyncSessionLocal()
        try:
            # Get date range - either custom or predefined period
            if custom_dates:
                start_date, end_date = custom_dates
                logger.info(
                    f"[Slackbot] Using custom date range: {start_date} to {end_date}"
                )
            else:
                start_date, end_date = get_date_range_for_period(
                    period, session, account_name
                )
                logger.info(
                    f"[Slackbot] Using {period} date range: {start_date} to {end_date}"
                )

            # Get timezone name for display
            if account_name:
                timezone_id = get_account_timezone(session, account_name)
            else:
                # Default to PST when no account specified
                timezone_id = "America/Los_Angeles"

            # Extract short timezone name (e.g., 'EST', 'PST')
            timezone_name = None
            if timezone_id:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(timezone_id)
                # Get timezone abbreviation
                now_in_tz = datetime.now(tz)
                timezone_name = now_in_tz.strftime("%Z")

            result = await send_report_to_slack(
                slack_channel,
                client,
                session,
                start_date,
                end_date,
                account_name,
                show_time=True,
                timezone_id=timezone_id,
                timezone_name=timezone_name,
                thread_ts=message.get("ts"),
            )
        finally:
            session.close()

        if result["status"] == "success":
            logger.info(
                f"[Slackbot] {period.capitalize()} report completed successfully"
            )
        else:
            # Send error message to Slack
            logger.error(
                f"[Slackbot] {period.capitalize()} report failed: {result['message']}"
            )
            try:
                await client.chat_postMessage(
                    channel=slack_channel, text=f"❌ {result['message']}", mrkdwn=True
                )
            except Exception as slack_error:
                logger.error(
                    f"[Slackbot] Failed to send error message to Slack: {slack_error}"
                )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling {period} request: {e}")
        # Try to send error to Slack
        try:
            slack_channel = message.get("channel")
            await client.chat_postMessage(
                channel=slack_channel,
                text=f"❌ An error occurred while processing your request: {str(e)}",
                mrkdwn=True,
            )
        except Exception:
            pass  # If we can't send to Slack, just log it


async def handle_last_hours_request(message, client):
    """
    Handle "last X hours" requests like "last 6 hours" or "last 12 hours for romeo".

    Args:
        message: Slack message object
        client: Slack client object
    """
    try:
        message_text = message.get("text", "")

        # Parse hours and account name from message
        hours = parse_last_hours(message_text)
        account_name = parse_account_name_from_message(message_text)

        if not hours:
            # Send help message if parsing failed
            slack_channel = message.get("channel")
            help_text = (
                "⏰ *Last X Hours Help*\n\n"
                "Please use the format: `last <number> hours`\n\n"
                "Examples:\n"
                "• `last 6 hours`\n"
                "• `last 12 hours for romeo`\n"
                "• `last 24 hours`\n\n"
                "Note: Maximum is 168 hours (7 days)"
            )

            await client.chat_postMessage(
                channel=slack_channel, text=help_text, mrkdwn=True
            )
            return

        # Get database session for timezone lookup
        session = SyncSessionLocal()
        try:
            slack_channel = message.get("channel")
            user = message["user"]

            # Get human-readable channel name for logging
            channel_name = await get_channel_name(client, slack_channel)

            logger.info(
                f"[Slackbot] User {user} requested last {hours} hours report in channel {channel_name}"
                + (f" for account '{account_name}'" if account_name else "")
            )

            # Calculate date range
            start_date, end_date = get_date_range_for_hours(
                hours, session, account_name
            )
            logger.info(
                f"[Slackbot] Using last {hours} hours range: {start_date} to {end_date}"
            )

            # Get timezone name for display
            if account_name:
                timezone_id = get_account_timezone(session, account_name)
            else:
                # Default to PST when no account specified
                timezone_id = "America/Los_Angeles"

            # Extract short timezone name (e.g., 'EST', 'PST')
            timezone_name = None
            if timezone_id:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(timezone_id)
                # Get timezone abbreviation
                now_in_tz = datetime.now(tz)
                timezone_name = now_in_tz.strftime("%Z")

            result = await send_report_to_slack(
                slack_channel,
                client,
                session,
                start_date,
                end_date,
                account_name,
                show_time=True,
                timezone_id=timezone_id,
                timezone_name=timezone_name,
                thread_ts=message.get("ts"),
            )

            if result["status"] == "success":
                logger.info(
                    f"[Slackbot] Last {hours} hours report completed successfully"
                )
            else:
                # Send error message to Slack
                logger.error(
                    f"[Slackbot] Last {hours} hours report failed: {result['message']}"
                )
                await client.chat_postMessage(
                    channel=slack_channel, text=f"❌ {result['message']}", mrkdwn=True
                )

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[Slackbot] Error handling last hours request: {e}")
        try:
            slack_channel = message.get("channel")
            await client.chat_postMessage(
                channel=slack_channel,
                text=f"❌ An error occurred while processing your request: {str(e)}",
                mrkdwn=True,
            )
        except Exception:
            pass


async def handle_custom_date_request(message, client):
    """
    Handle custom date range requests like "From 2024-01-01 to 2024-01-31".

    Args:
        message: Slack message object
        client: Slack client object
    """
    try:
        message_text = message.get("text", "")

        # Parse account name from message if provided
        account_name = parse_account_name_from_message(message_text)

        # Get database session to look up timezone
        session = SyncSessionLocal()
        try:
            custom_dates = parse_custom_date_range(message_text, session, account_name)

            if custom_dates:
                await handle_report_request("custom", message, client, custom_dates)
            else:
                # Send help message if parsing failed
                slack_channel = message.get("channel")
                help_text = (
                    "📅 *Custom Date Range Help*\n\n"
                    "Please use the format: `From YYYY-MM-DD [HH:MM] to YYYY-MM-DD [HH:MM]`\n\n"
                    "Examples:\n"
                    "• `From 2024-01-01 to 2024-01-31` (full days)\n"
                    "• `From 2024-01-01 10:00 to 2024-01-31 15:30` (with specific times)\n"
                    "• `From 2024-01-15 9:00 to 2024-01-15 17:00` (same day)\n\n"
                    "Note: Times are in 24-hour format (HH:MM)"
                )

                await client.chat_postMessage(
                    channel=slack_channel, text=help_text, mrkdwn=True
                )
        finally:
            session.close()

    except Exception as e:
        logger.error(f"[Slackbot] Error handling custom date request: {e}")
