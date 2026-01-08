"""
Slack Report Orchestration Module

This module orchestrates report generation by coordinating with analytics service,
formatting data, and sending to Slack.
"""

from datetime import datetime, timedelta

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from services.analytics_service import get_reports
from services.analytics_service._utils import normalize_datetime_to_utc
from utils.log import logger

from ._access_control import determine_account_filter
from ._client import DEFAULT_SLACK_CHANNEL, get_slack_client
from ._formatting import format_unified_report_for_slack
from ._messages import send_slack_message

# =============================================================================
# DATE RANGE UTILITY FUNCTIONS
# =============================================================================


def get_date_range_for_hours(hours: int) -> tuple[datetime, datetime]:
    """
    Generate start_date and end_date for custom hour range.

    Args:
        hours: Number of hours to look back

    Returns:
        tuple[datetime, datetime]: (start_date, end_date) in UTC
    """
    # Always use PST timezone
    from zoneinfo import ZoneInfo

    timezone_id = "America/Los_Angeles"
    tz = ZoneInfo(timezone_id)
    now = datetime.now(tz)
    logger.info(
        f"[Slackbot] Calculating last {hours} hours in timezone '{timezone_id}': {now}"
    )

    # Calculate start date by subtracting hours
    start_date = now - timedelta(hours=hours)
    end_date = now

    # Normalize both dates to ensure they are timezone-aware UTC
    start_date = normalize_datetime_to_utc(start_date)
    end_date = normalize_datetime_to_utc(end_date)

    return start_date, end_date


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    """
    Generate start_date and end_date for different reporting periods.

    Args:
        period: "daily", "weekly", or "monthly"

    Returns:
        tuple[datetime, datetime]: (start_date, end_date) in UTC
    """
    # Always use PST timezone
    from zoneinfo import ZoneInfo

    timezone_id = "America/Los_Angeles"
    tz = ZoneInfo(timezone_id)
    now = datetime.now(tz)
    logger.info(
        f"[Slackbot] Calculating {period} date range in timezone '{timezone_id}': {now}"
    )

    if period == "daily":
        # Daily: yesterday this time to now (24-hour rolling window)
        start_date = now - timedelta(days=1)
        end_date = now

    elif period == "weekly":
        # Weekly: 7 days ago at 00:00 to today at 00:00 (clean week boundaries)
        start_date = (now - timedelta(days=7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    elif period == "monthly":
        # Monthly: first day of previous month to first day of current month
        first_day_current = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        if now.month == 1:
            first_day_previous = first_day_current.replace(year=now.year - 1, month=12)
        else:
            first_day_previous = first_day_current.replace(month=now.month - 1)

        start_date = first_day_previous
        end_date = first_day_current

    else:
        raise ValueError(
            f"Unsupported period: {period}. Use 'daily', 'weekly', or 'monthly'"
        )

    # Normalize both dates to ensure they are timezone-aware UTC
    start_date = normalize_datetime_to_utc(start_date)
    end_date = normalize_datetime_to_utc(end_date)

    return start_date, end_date


# =============================================================================
# SLACK INTERACTION FUNCTIONS
# =============================================================================


async def get_channel_name(client: AsyncWebClient, channel_id: str) -> str:
    """
    Get human-readable channel name from channel ID.

    Args:
        client: Slack async web client
        channel_id: Slack channel ID (e.g., 'C09BT1E5E7M')

    Returns:
        Channel name with # prefix (e.g., '#general') or original ID if lookup fails
    """
    try:
        response = await client.conversations_info(channel=channel_id)
        if response and response.get("ok"):
            channel_info = response.get("channel")
            if channel_info:
                channel_name = channel_info.get("name")
                if channel_name:
                    return f"#{channel_name}"
    except Exception as e:
        logger.warning(f"[Slackbot] Failed to get channel name for {channel_id}: {e}")

    # Fallback to channel ID if lookup fails
    return channel_id


# =============================================================================
# MAIN REPORT GENERATION FUNCTION
# =============================================================================


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
    Send a comprehensive analytics report to Slack.

    Args:
        slack_channel: Slack channel to send to (optional, defaults to DEFAULT_SLACK_CHANNEL if not provided).
                      Sets target_channel to slack_channel or DEFAULT_SLACK_CHANNEL.
        client: Optional async Slack client to reuse. If not provided, obtains one via
                get_slack_client() (catches ValueError if token not configured).
        session: Database session for fetching analytics data
        start_date: Start date for the report (in UTC)
        end_date: End date for the report (in UTC)
        account_name: Optional account name to filter by (from message like "daily for acme")
        show_time: If True, show full datetime with time and timezone in report title
        timezone_id: Timezone ID to convert UTC times to local time (e.g., 'America/New_York')
        timezone_name: Timezone abbreviation to display (e.g., 'EST', 'PST')

    Returns:
        dict: Status of the operation
    """
    try:
        # Validate required session
        if session is None:
            return {"status": "error", "message": "Database session not available"}

        # Get target channel
        target_channel = slack_channel or DEFAULT_SLACK_CHANNEL

        # Create client if not provided
        if client is None:
            try:
                client = await run_in_threadpool(get_slack_client)
            except ValueError as e:
                return {"status": "error", "message": str(e)}

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

        # Send to Slack using the new generic function
        logger.info(f"[Slackbot] Sending report to Slack channel: {target_channel}")
        result = await send_slack_message(
            blocks=message_blocks["blocks"],
            channel=target_channel,
            text_fallback="Analytics Report",
            client=client,
        )

        if result["status"] == "success":
            logger.info(f"[Slackbot] Report sent successfully to {target_channel}")
            return {
                "status": "success",
                "message": f"Report sent to {target_channel} successfully",
            }
        else:
            logger.error(f"[Slackbot] Failed to send report: {result['message']}")
            return result

    except SlackApiError as e:
        error_msg = f"Slack API error: {e.response['error']}"
        logger.error(f"[Slackbot] {error_msg}")
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Failed to send report: {str(e)}"
        logger.error(f"[Slackbot] {error_msg}")
        return {"status": "error", "message": error_msg}
