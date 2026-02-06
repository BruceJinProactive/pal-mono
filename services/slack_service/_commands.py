"""
Slack Command Parsing and Routing Module

This module handles parsing of Slack commands and routing them to appropriate handlers.
"""

import re
from datetime import datetime

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


def parse_custom_date_range(message_text: str) -> tuple[datetime, datetime] | None:
    """
    Parse custom date range from message text like "from 2024-01-01 to 2024-01-31" or "from 2024-01-01 10:00 to 2024-01-31 15:30".
    Supports YYYY-MM-DD format and optional HH:MM time with case-insensitive matching.

    Args:
        message_text: The full message text from Slack

    Returns:
        tuple[datetime, datetime] | None: (start_date, end_date) in UTC, or None if no match
    """
    # Import here to avoid circular dependency
    from services.analytics_service._utils import normalize_datetime_to_utc

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

        # Always use PST timezone
        from zoneinfo import ZoneInfo

        timezone_id = "America/Los_Angeles"
        tz = ZoneInfo(timezone_id)
        start_date = start_date.replace(tzinfo=tz)
        end_date = end_date.replace(tzinfo=tz)
        start_date = normalize_datetime_to_utc(start_date)
        end_date = normalize_datetime_to_utc(end_date)

        start_display = (
            f"{start_date_str} {start_time_str}" if start_time_str else start_date_str
        )
        end_display = f"{end_date_str} {end_time_str}" if end_time_str else end_date_str

        logger.info(
            f"[Slackbot] Parsed dates in timezone 'PST/PDT': {start_display} -> {start_date}, {end_display} -> {end_date}"
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
                start_date, end_date = get_date_range_for_period(period)
                logger.info(
                    f"[Slackbot] Using {period} date range: {start_date} to {end_date}"
                )

            # Always use PST timezone
            timezone_id = "America/Los_Angeles"

            # Extract short timezone name (e.g., 'PST', 'PDT')
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(timezone_id)
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
        except Exception as slack_error:
            logger.error(
                f"[Slackbot] Failed to send error message to Slack: {slack_error}"
            )


async def handle_last_hours_request(message, client):
    """
    Handle "last X hours" requests like "last 6 hours" or "last 12 hours for romeo".

    Args:
        message: Slack message object
        client: Slack client object
    """
    # Import here to avoid circular dependency
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

        # Get database session for conversion data using proper context handling
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
            start_date, end_date = get_date_range_for_hours(hours)
            logger.info(
                f"[Slackbot] Using last {hours} hours range: {start_date} to {end_date}"
            )

            # Always use PST timezone
            timezone_id = "America/Los_Angeles"

            # Extract short timezone name (e.g., 'PST', 'PDT')
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(timezone_id)
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
        except Exception as slack_error:
            logger.error(
                f"[Slackbot] Failed to send error message to Slack: {slack_error}"
            )


async def handle_custom_date_request(message, client):
    """
    Handle custom date range requests like "From 2024-01-01 to 2024-01-31".

    Args:
        message: Slack message object
        client: Slack client object
    """
    try:
        message_text = message.get("text", "")

        # Parse custom date range (always uses PST)
        custom_dates = parse_custom_date_range(message_text)

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

    except Exception as e:
        logger.error(f"[Slackbot] Error handling custom date request: {e}")


async def handle_feedback_status_request(message, client):
    """
    Handle feedback-status requests like "/feedback-status client-name" or "feedback-status for client-name".

    Shows ALL feedback for the specified client, grouped by status type.

    Queries Notion ONLY (no database queries).

    Args:
        message: Slack message object
        client: Slack client object
    """
    from collections import defaultdict

    from services import notion_service

    try:
        slack_channel = message.get("channel")
        user = message["user"]
        message_text = message.get("text", "")

        # Parse client name from message
        # Support formats: "feedback-status client-name", "feedback-status for client-name", "/feedback-status client-name"
        client_name = None

        # Try "for client-name" format first
        client_name = parse_account_name_from_message(message_text)

        # If not found, try to extract client name directly after "feedback-status"
        if not client_name:
            match = re.search(
                r"feedback-status\s+([a-zA-Z0-9_-]+)", message_text, re.IGNORECASE
            )
            if match:
                client_name = match.group(1).strip()

        if not client_name:
            # Send help message if parsing failed
            help_text = (
                "📊 *Feedback Status Command Help*\n\n"
                "Please use the format: `feedback-status <client-name>` or `feedback-status for <client-name>`\n\n"
                "Examples:\n"
                "• `feedback-status acme-restaurant`\n"
                "• `feedback-status for burger-place`\n"
                "• `/feedback-status romeo`\n\n"
                "This will show all feedback for the specified client, grouped by status."
            )

            await client.chat_postMessage(
                channel=slack_channel, text=help_text, mrkdwn=True
            )
            return

        logger.info(
            f"[Slackbot] User {user} requested feedback status for client '{client_name}' in channel {slack_channel}"
        )

        # Send processing message
        await client.chat_postMessage(
            channel=slack_channel,
            text=f"🔍 Fetching feedback status for *{client_name}*...",
            mrkdwn=True,
        )

        # Query Notion for ALL feedback tickets for this client (all statuses)
        all_feedbacks = await notion_service.get_feedback_tickets_by_client(client_name)

        if not all_feedbacks:
            await client.chat_postMessage(
                channel=slack_channel,
                text=f"✅ No feedback found for *{client_name}*.",
                mrkdwn=True,
            )
            return

        # Group feedback by status
        status_groups = defaultdict(list)
        for ticket in all_feedbacks:
            status = ticket.get("status") or "New"
            status_groups[status].append(ticket)

        # Define status order for display
        status_order = [
            "New",
            "Investigating",
            "Changes Now Live",
            "Resolved",
            "Out of Scope",
        ]

        # Add any unexpected statuses to the end (so we don't drop them)
        for status in status_groups.keys():
            if status not in status_order:
                status_order.append(status)

        # Build response message
        response_lines = [
            f"📊 *Feedback Status for `{client_name}`*",
            f"Found *{len(all_feedbacks)}* feedback item{'s' if len(all_feedbacks) != 1 else ''}:\n",
        ]

        total_shown = 0
        for status in status_order:
            if status not in status_groups:
                continue

            feedbacks_in_status = status_groups[status]

            # Add status header with count
            status_emoji = {
                "New": "🆕",
                "Investigating": "👀",
                "Changes Now Live": "✅",
                "Resolved": "✔️",
                "Out of Scope": "🚫",
            }.get(status, "📌")

            response_lines.append(
                f"\n*{status_emoji} {status}* ({len(feedbacks_in_status)} items)"
            )

            # Sort by created_time (most recent first)
            feedbacks_in_status.sort(
                key=lambda x: x.get("created_time", ""), reverse=True
            )

            # Show up to 5 items per status
            for ticket in feedbacks_in_status[:5]:
                # Format date
                created_time_str = ticket.get("created_time") or ""
                try:
                    created_dt = datetime.fromisoformat(
                        created_time_str.replace("Z", "+00:00")
                    )
                    created_date = created_dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    created_date = "Unknown date"

                # Get feedback text (truncate if too long)
                feedback_text = ticket.get("feedback_text") or "(No text provided)"
                if len(feedback_text) > 80:
                    feedback_text = feedback_text[:80] + "..."

                # Get tags
                tags_display = ""
                tags = ticket.get("tags", [])
                if tags:
                    tags_display = f" | _Tags: {', '.join(tags)}_"

                # Add to response
                response_lines.append(
                    f"  • {created_date} | {feedback_text}{tags_display}"
                )
                total_shown += 1

            if len(feedbacks_in_status) > 5:
                response_lines.append(f"  _...and {len(feedbacks_in_status) - 5} more_")

        if total_shown < len(all_feedbacks):
            response_lines.append(
                f"\n_Showing {total_shown} of {len(all_feedbacks)} feedback items._"
            )

        await client.chat_postMessage(
            channel=slack_channel, text="\n".join(response_lines), mrkdwn=True
        )

        logger.info(
            f"[Slackbot] Returned feedback status for {client_name}: {len(all_feedbacks)} total items"
        )

    except Exception as e:
        logger.error(
            f"[Slackbot] Error handling feedback status request: {e}", exc_info=True
        )
        try:
            slack_channel = message.get("channel")
            await client.chat_postMessage(
                channel=slack_channel,
                text=f"❌ An error occurred while fetching feedback: {str(e)}",
                mrkdwn=True,
            )
        except Exception as slack_error:
            logger.error(
                f"[Slackbot] Failed to send error message to Slack: {slack_error}"
            )


async def handle_feedback_all_clients_summary(message, client):
    """
    Show summary of all clients with unresolved feedback.

    Unresolved feedback = status "New" or "Investigating"

    Args:
        message: Slack message object
        client: Slack client object
    """
    from services import notion_service

    try:
        slack_channel = message.get("channel")
        user = message["user"]

        logger.info(
            f"[Slackbot] User {user} requested unresolved feedback summary for all clients"
        )

        # Send processing message
        await client.chat_postMessage(
            channel=slack_channel,
            text="🔍 Fetching unresolved feedback for all clients...",
            mrkdwn=True,
        )

        # Query Notion for unresolved feedback across all clients
        tickets_by_account = await notion_service.get_all_feedback_tickets(
            exclude_resolved=True
        )

        if not tickets_by_account:
            await client.chat_postMessage(
                channel=slack_channel,
                text="✅ No unresolved feedback found for any client.",
                mrkdwn=True,
            )
            return

        # Count tickets per account
        account_counts = {
            account_name: len(tickets)
            for account_name, tickets in tickets_by_account.items()
        }

        # Sort by count (descending)
        sorted_accounts = sorted(
            account_counts.items(), key=lambda x: x[1], reverse=True
        )

        total_unresolved = sum(account_counts.values())

        # Build response
        response_lines = [
            "📋 *Clients with Unresolved Feedback*",
            f"Found *{len(sorted_accounts)}* clients with *{total_unresolved}* total unresolved items:\n",
        ]

        for account_name, count in sorted_accounts[:20]:
            # Urgency indicator
            emoji = "🔴" if count >= 10 else "🟡" if count >= 5 else "🟢"
            response_lines.append(
                f"{emoji} *`{account_name}`*: {count} item{'s' if count != 1 else ''}"
            )

        if len(sorted_accounts) > 20:
            response_lines.append(
                f"\n_Showing top 20 of {len(sorted_accounts)} clients._"
            )

        response_lines.append(
            "\n_Use `feedback <client-name>` to see details for a specific client._"
        )

        await client.chat_postMessage(
            channel=slack_channel, text="\n".join(response_lines), mrkdwn=True
        )

        logger.info(
            f"[Slackbot] Returned summary: {len(sorted_accounts)} clients, {total_unresolved} total items"
        )

    except Exception as e:
        logger.error(f"[Slackbot] Error fetching feedback summary: {e}", exc_info=True)
        try:
            await client.chat_postMessage(
                channel=message.get("channel"),
                text=f"❌ Error fetching feedback: {str(e)}",
                mrkdwn=True,
            )
        except Exception as slack_error:
            logger.error(f"[Slackbot] Failed to send error: {slack_error}")


async def handle_feedback_request(message, client):
    """
    Handle feedback requests:
    - "feedback" (no client) - Shows all clients with unresolved feedback
    - "feedback <client-name>" - Shows unresolved feedback for specific client

    Unresolved feedback = status "New" or "Investigating" (NOT resolved/closed)

    Args:
        message: Slack message object
        client: Slack client object
    """
    from services import notion_service

    try:
        slack_channel = message.get("channel")
        user = message["user"]
        message_text = message.get("text", "")

        # Parse client name from message
        client_name = parse_account_name_from_message(message_text)
        if not client_name:
            # Try extracting client name directly after "feedback"
            match = re.search(
                r"feedback\s+([a-zA-Z0-9_-]+)", message_text, re.IGNORECASE
            )
            if match:
                client_name = match.group(1).strip()

        # If no client name, show summary for all clients
        if not client_name:
            await handle_feedback_all_clients_summary(message, client)
            return

        logger.info(
            f"[Slackbot] User {user} requested unresolved feedback for '{client_name}'"
        )

        # Send processing message
        await client.chat_postMessage(
            channel=slack_channel,
            text=f"🔍 Fetching unresolved feedback for *{client_name}*...",
            mrkdwn=True,
        )

        # Query Notion for unresolved feedback (status: New or Investigating)
        unresolved_feedbacks = await notion_service.get_feedback_tickets_by_client(
            client_name, exclude_resolved=True
        )

        if not unresolved_feedbacks:
            await client.chat_postMessage(
                channel=slack_channel,
                text=f"✅ No unresolved feedback for *{client_name}*!",
                mrkdwn=True,
            )
            return

        # Sort by most recent first
        unresolved_feedbacks.sort(key=lambda x: x.get("created_time", ""), reverse=True)

        # Build response
        response_lines = [
            f"📋 *Unresolved Feedback for `{client_name}`*",
            f"Found *{len(unresolved_feedbacks)}* unresolved item{'s' if len(unresolved_feedbacks) != 1 else ''}:\n",
        ]

        for i, ticket in enumerate(unresolved_feedbacks[:10], 1):
            # Format date
            created_time_str = ticket.get("created_time") or ""
            try:
                created_dt = datetime.fromisoformat(
                    created_time_str.replace("Z", "+00:00")
                )
                created_date = created_dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                created_date = "Unknown date"

            # Get feedback text
            feedback_text = ticket.get("feedback_text") or "(No text provided)"
            if len(feedback_text) > 100:
                feedback_text = feedback_text[:100] + "..."

            # Get status
            status = ticket.get("status") or "New"
            status_emoji = "🆕" if status == "New" else "👀"

            # Get tags
            tags = ticket.get("tags", [])
            tags_display = f"\n   _Tags: {', '.join(tags)}_" if tags else ""

            # Get user
            user_name = ticket.get("user_name") or ticket.get("user_email") or "Unknown"

            response_lines.append(
                f"*{i}.* {status_emoji} *{status}* | {created_date}\n"
                f"   {feedback_text}{tags_display}\n"
                f"   _User: {user_name}_\n"
                f"   _Conversation ID: `{ticket.get('conversation_id')}`_\n"
            )

        if len(unresolved_feedbacks) > 10:
            response_lines.append(
                f"\n_Showing 10 of {len(unresolved_feedbacks)} unresolved items._"
            )

        await client.chat_postMessage(
            channel=slack_channel, text="\n".join(response_lines), mrkdwn=True
        )

        logger.info(
            f"[Slackbot] Returned {len(unresolved_feedbacks)} unresolved items for {client_name}"
        )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling feedback request: {e}", exc_info=True)
        try:
            await client.chat_postMessage(
                channel=message.get("channel"),
                text=f"❌ Error fetching feedback: {str(e)}",
                mrkdwn=True,
            )
        except Exception as slack_error:
            logger.error(f"[Slackbot] Failed to send error: {slack_error}")
