"""
Slack Command Parsing and Routing Module

This module handles parsing of Slack commands and routing them to appropriate handlers.
"""

import re
from datetime import datetime

from sqlalchemy.orm import Session

from db.session import SyncSessionLocal
from utils.log import logger

# =============================================================================
# COMMAND PARSING FUNCTIONS
# =============================================================================


def parse_account_name_from_message(message_text: str) -> str | None:
    """
    Parse account name from message text like "daily for acme-restaurant".
    Only supports "for" keyword format.

    Args:
        message_text: The full message text from Slack

    Returns:
        str | None: Account name if found, None otherwise
    """
    # Pattern: "for account_name" (case insensitive)
    match = re.search(r"for\s+([a-zA-Z0-9_-]+)", message_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


def parse_last_hours(message_text: str) -> int | None:
    """
    Parse "last X hours" from message text.

    Args:
        message_text: The full message text from Slack

    Returns:
        int | None: Number of hours if found, None otherwise

    Examples:
        "last 6 hours" -> 6
        "last 12 hours for romeo" -> 12
        "last 24 hours" -> 24
    """
    # Pattern: "last <number> hours" (case insensitive)
    pattern = r"last\s+(\d+)\s+hours?"
    match = re.search(pattern, message_text, re.IGNORECASE)

    if match:
        hours = int(match.group(1))
        if hours > 0 and hours <= 168:  # Max 7 days (168 hours)
            return hours
        else:
            logger.warning(
                f"[Slackbot] Invalid hours value: {hours}. Must be between 1 and 168."
            )
            return None

    return None


def parse_custom_date_range(
    message_text: str, session: Session | None = None, account_name: str | None = None
) -> tuple[datetime, datetime] | None:
    """
    Parse custom date range from message text like "from 2024-01-01 to 2024-01-31" or "from 2024-01-01 10:00 to 2024-01-31 15:30".
    Supports YYYY-MM-DD format and optional HH:MM time with case-insensitive matching.

    Args:
        message_text: The full message text from Slack
        session: Database session (optional) - used to look up account timezone
        account_name: Account name (optional) - if provided, dates are interpreted in account's timezone

    Returns:
        tuple[datetime, datetime] | None: (start_date, end_date) in UTC, or None if no match
    """
    # Import here to avoid circular dependency
    from services.analytics_service._utils import normalize_datetime_to_utc

    from ._access_control import get_account_timezone

    # Pattern to match "from YYYY-MM-DD [HH:MM] to YYYY-MM-DD [HH:MM]" format (case insensitive)
    # Time is optional, format: HH:MM (24-hour)
    pattern = r"from\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\s+to\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?"
    match = re.search(pattern, message_text, re.IGNORECASE)

    if not match:
        return None

    start_date_str = match.group(1).strip()
    start_time_str = match.group(2)  # Optional time for start
    end_date_str = match.group(3).strip()
    end_time_str = match.group(4)  # Optional time for end

    try:
        # Parse dates - start with just the date part
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

        # If time is provided, parse and apply it; otherwise use default times
        if start_time_str:
            # Parse time (HH:MM format)
            time_parts = start_time_str.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            start_date = start_date.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
        else:
            # Default to beginning of day (00:00:00)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if end_time_str:
            # Parse time (HH:MM format)
            time_parts = end_time_str.split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            end_date = end_date.replace(
                hour=hour, minute=minute, second=59, microsecond=999999
            )
        else:
            # Default to end of day (23:59:59)
            end_date = end_date.replace(
                hour=23, minute=59, second=59, microsecond=999999
            )

        # Get account timezone if available, otherwise default to PST
        timezone_id = None
        if session and account_name:
            timezone_id = get_account_timezone(session, account_name)

        if not timezone_id:
            # Default to PST when no account specified
            timezone_id = "America/Los_Angeles"

        # Interpret dates in timezone (account's or PST), then convert to UTC
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone_id)
        start_date = start_date.replace(tzinfo=tz)
        end_date = end_date.replace(tzinfo=tz)
        start_date = normalize_datetime_to_utc(start_date)
        end_date = normalize_datetime_to_utc(end_date)

        start_display = (
            f"{start_date_str} {start_time_str}" if start_time_str else start_date_str
        )
        end_display = f"{end_date_str} {end_time_str}" if end_time_str else end_date_str

        tz_display = (
            "PST/PDT"
            if timezone_id == "America/Los_Angeles" and not account_name
            else timezone_id
        )
        logger.info(
            f"[Slackbot] Parsed dates in timezone '{tz_display}': {start_display} -> {start_date}, {end_display} -> {end_date}"
        )

        return start_date, end_date

    except ValueError as e:
        start_display = (
            f"{start_date_str} {start_time_str}" if start_time_str else start_date_str
        )
        end_display = f"{end_date_str} {end_time_str}" if end_time_str else end_date_str
        logger.warning(
            f"[Slackbot] Failed to parse date range '{start_display}' to '{end_display}': {e}"
        )
        return None


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


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
    # Import here to avoid circular dependency
    from ._access_control import get_account_timezone
    from ._reports import (
        get_channel_name,
        get_date_range_for_period,
        send_report_to_slack,
    )

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
    # Import here to avoid circular dependency
    from ._access_control import get_account_timezone
    from ._reports import (
        get_channel_name,
        get_date_range_for_hours,
        send_report_to_slack,
    )

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
