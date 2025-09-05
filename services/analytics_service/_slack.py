"""
Slack Analytics Bot Service

This module provides Slack integration for analytics reporting, including:
- Automated report generation and formatting
- Custom date range parsing
- Interactive Slack bot commands
- Professional table formatting for analytics data

The service supports daily, weekly, monthly, and custom date range reports
with engagement metrics, conversion data, and call quality analytics.
"""

import re
import threading
from datetime import datetime, timedelta

from fastapi.responses import JSONResponse, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from db.session import SyncSessionLocal
from services.analytics_service._implementation import get_reports
from services.analytics_service._utils import normalize_datetime_to_utc
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Report name to data key mapping for cleaner code
REPORT_DATA_KEYS = {
    "Active Users": "active_users",
    "Message Turn Distribution": "turn_distribution",
    "Call Time Metrics": "call_time_metrics",
    "Conversion Metrics": "conversion_metrics",
}

# Conversion metrics keys for data detection
CONVERSION_METRIC_KEYS = [
    "conversations_with_orders",
    "paid_orders",
    "total_subtotal",
    "paid_total",
    "conversion_rate",
    "paid_rate",
]

# Column definitions for different report sections
ENGAGEMENT_COLUMNS = [
    "active_users",
    "total_conversations",
    "total_turns",
    "avg_turns",
    "total_calls",
    "avg_duration",
    "transfer_calls",
    "transfer_rate",
    "positive_calls",
    "negative_calls",
]

CONVERSION_COLUMNS = [
    "conversations_with_orders",
    "paid_orders",
    "total_subtotal",
    "paid_total",
    "conversion_rate",
    "paid_rate",
]

ALL_COLUMNS = ENGAGEMENT_COLUMNS + CONVERSION_COLUMNS

# Global Slack app instance and thread safety
_slack_app = None
_slack_handler = None
_slack_init_lock = threading.Lock()


# =============================================================================
# DATE UTILITY FUNCTIONS
# =============================================================================


def parse_custom_date_range(message_text: str) -> tuple[datetime, datetime] | None:
    """
    Parse custom date range from message text like "from 2024-01-01 to 2024-01-31".
    Supports YYYY-MM-DD format with case-insensitive matching.

    Args:
        message_text: The full message text from Slack

    Returns:
        tuple[datetime, datetime] | None: (start_date, end_date) in UTC, or None if no match
    """
    # Pattern to match "from YYYY-MM-DD to YYYY-MM-DD" format (case insensitive)
    pattern = r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})"
    match = re.search(pattern, message_text, re.IGNORECASE)

    if not match:
        return None

    start_str = match.group(1).strip()
    end_str = match.group(2).strip()

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")
        start_date = normalize_datetime_to_utc(start_date)
        end_date = normalize_datetime_to_utc(end_date)

        return start_date, end_date

    except ValueError as e:
        logger.warning(
            f"[Slackbot] Failed to parse date range '{start_str}' to '{end_str}': {e}"
        )
        return None


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    """
    Generate start_date and end_date for different reporting periods.

    Args:
        period: "daily", "weekly", or "monthly"

    Returns:
        tuple[datetime, datetime]: (start_date, end_date) in UTC
    """
    now = datetime.utcnow()
    now = normalize_datetime_to_utc(now)

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


# FORMATTING UTILITY FUNCTIONS
# =============================================================================


def safe_float_format(value, decimals: int = 1) -> str:
    """Safely format a value as float, handling strings and None."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def create_column_config(key: str, header: str, format_type: str = "int") -> dict:
    """Create a standardized column configuration."""
    format_funcs = {
        "int": lambda x: str(x) if x is not None else "N/A",
        "float": lambda x: safe_float_format(x, 1),
        "percent": lambda x: f"{safe_float_format(x, 1)}%" if x is not None else "N/A",
        "currency": lambda x: f"${safe_float_format(x, 2)}" if x is not None else "N/A",
        "duration": lambda x: f"{safe_float_format(x, 1)}s" if x is not None else "N/A",
    }

    return {
        "header": header,
        "data_key": key,
        "format_func": format_funcs.get(format_type, format_funcs["int"]),
    }


# Column configuration for unified reports
REPORT_COLUMNS = {
    # Engagement metrics
    "active_users": create_column_config("active_users", "Active Users"),
    "total_conversations": create_column_config("total_conversations", "Total Conv"),
    "total_turns": create_column_config("total_turns", "Total Turns"),
    "avg_turns": create_column_config("avg_turns", "Avg Turns", "float"),
    "total_calls": create_column_config("total_calls", "Total Calls"),
    "avg_duration": create_column_config("avg_duration", "Avg Duration", "duration"),
    "transfer_calls": create_column_config("transfer_calls", "Transfer Calls"),
    "transfer_rate": create_column_config("transfer_rate", "Transfer Rate", "percent"),
    "positive_calls": create_column_config("positive_calls", "Positive Calls"),
    "negative_calls": create_column_config("negative_calls", "Negative Calls"),
    # Conversion metrics
    "conversations_with_orders": create_column_config(
        "conversations_with_orders", "Conv w/ Orders"
    ),
    "paid_orders": create_column_config("paid_orders", "Paid Orders"),
    "total_subtotal": create_column_config(
        "total_subtotal", "Total Revenue", "currency"
    ),
    "paid_total": create_column_config("paid_total", "Paid Revenue", "currency"),
    "conversion_rate": create_column_config(
        "conversion_rate", "Conversion Rate", "percent"
    ),
    "paid_rate": create_column_config("paid_rate", "Paid Rate", "percent"),
}


# =============================================================================
# DATA PROCESSING FUNCTIONS
# =============================================================================


def merge_report_data(reports: list) -> dict:
    """
    Merge multiple report types into unified account data structure.

    Args:
        reports: List of report objects with name and data attributes

    Returns:
        dict: Unified account data with all metrics
    """
    unified_accounts = {}
    totals_summary = {}

    # Process each report type
    for report in reports:
        report_name = report.name
        report_data = report.data

        # Extract totals for summary
        if "totals" in report_data:
            totals_summary[report_name] = report_data["totals"]

        # Extract account-level data
        account_data_key = REPORT_DATA_KEYS.get(report_name)
        if account_data_key and account_data_key in report_data:
            accounts = report_data[account_data_key]

            for account_name, metrics in accounts.items():
                if account_name not in unified_accounts:
                    unified_accounts[account_name] = {}

                # Merge metrics into unified structure
                unified_accounts[account_name].update(metrics)

    return {"unified_accounts": unified_accounts, "totals_summary": totals_summary}


def has_conversion_data(totals_summary: dict, unified_accounts: dict) -> bool:
    """Check if conversion data exists in the reports."""
    return "Conversion Metrics" in totals_summary or any(
        any(key in account_data for key in CONVERSION_METRIC_KEYS)
        for account_data in unified_accounts.values()
    )


# =============================================================================
# TABLE CREATION FUNCTIONS
# =============================================================================


def create_account_metrics_table(unified_accounts: dict, columns: list[str]) -> str:
    """Create a proper ASCII table format like the example provided."""
    if not unified_accounts:
        return "No account data available."

    # Get headers
    headers = ["Account"] + [
        REPORT_COLUMNS[col]["header"] for col in columns if col in REPORT_COLUMNS
    ]

    # Build data rows
    data_rows = []
    for account_name, account_data in unified_accounts.items():
        row = [account_name]
        for col_key in columns:
            if col_key in REPORT_COLUMNS:
                col_config = REPORT_COLUMNS[col_key]
                value = account_data.get(col_config["data_key"])
                formatted_value = col_config["format_func"](value)
                # Remove currency symbols and % for cleaner table display
                if formatted_value.startswith("$"):
                    formatted_value = formatted_value[1:]
                if formatted_value.endswith("%"):
                    formatted_value = formatted_value[:-1]
                row.append(formatted_value)
        data_rows.append(row)

    # Calculate column widths
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in data_rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))
        col_widths.append(max_width)

    lines = []

    # Header row
    header_line = ""
    for i, header in enumerate(headers):
        if i == 0:
            # Left-align account names
            header_line += header.ljust(col_widths[i])
        else:
            # Right-align numeric columns
            header_line += header.rjust(col_widths[i])
        if i < len(headers) - 1:
            header_line += "  "
    lines.append(header_line)

    # Separator line
    separator = ""
    for i, width in enumerate(col_widths):
        separator += "-" * width
        if i < len(col_widths) - 1:
            separator += "--"
    lines.append(separator)

    # Data rows
    for row in data_rows:
        row_line = ""
        for i, cell in enumerate(row):
            cell_str = str(cell)
            if i == 0:
                # Left-align account names
                row_line += cell_str.ljust(col_widths[i])
            else:
                # Right-align numeric values
                row_line += cell_str.rjust(col_widths[i])
            if i < len(row) - 1:
                row_line += "  "
        lines.append(row_line)

    return "```\n" + "\n".join(lines) + "\n```"


def create_conversion_table(unified_accounts: dict) -> str:
    """Create a conversion table similar to the provided example format."""
    if not unified_accounts:
        return "No account data available."

    # Headers matching the example format
    headers = ["Account", "Conv", "Orders", "Paid", "CVR%", "Paid%"]

    # Build data rows
    data_rows = []
    for account_name, account_data in unified_accounts.items():
        conv = account_data.get("total_conversations", "0")
        orders = account_data.get("conversations_with_orders", "0")
        paid = account_data.get("paid_orders", "0")
        cvr = safe_float_format(account_data.get("conversion_rate", 0), 1)
        paid_rate = safe_float_format(account_data.get("paid_rate", 0), 1)

        row = [account_name, str(conv), str(orders), str(paid), cvr, paid_rate]
        data_rows.append(row)

    # Calculate column widths with minimum widths for numeric columns
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in data_rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))

        # Set minimum widths based on column type for conversion table
        if i > 0:  # Skip account name column
            if header in ["Conv"]:
                # Conversations: 10 digits (9,999,999,999)
                max_width = max(max_width, 10)
            else:
                # Other numeric columns: keep existing 6 digit width
                max_width = max(max_width, 6)

        col_widths.append(max_width)

    lines = []

    # Header row
    header_line = ""
    for i, header in enumerate(headers):
        if i == 0:
            # Left-align account names
            header_line += header.ljust(col_widths[i])
        else:
            # Right-align numeric columns
            header_line += header.rjust(col_widths[i])
        if i < len(headers) - 1:
            header_line += "  "
    lines.append(header_line)

    # Separator line
    separator = ""
    for i, width in enumerate(col_widths):
        separator += "-" * width
        if i < len(col_widths) - 1:
            separator += "--"
    lines.append(separator)

    # Data rows
    for row in data_rows:
        row_line = ""
        for i, cell in enumerate(row):
            cell_str = str(cell)
            if i == 0:
                # Left-align account names
                row_line += cell_str.ljust(col_widths[i])
            else:
                # Right-align numeric values
                row_line += cell_str.rjust(col_widths[i])
            if i < len(row) - 1:
                row_line += "  "
        lines.append(row_line)

    return "```\n" + "\n".join(lines) + "\n```"


def create_engagement_table(unified_accounts: dict) -> str:
    """Create an engagement table with key metrics including call quality."""
    if not unified_accounts:
        return "No account data available."

    # Headers with key engagement metrics
    headers = ["Account", "Users", "Conv", "Calls", "Dur", "Xfer%"]

    # Build data rows
    data_rows = []
    for account_name, account_data in unified_accounts.items():
        users = account_data.get("active_users", "0")
        conv = account_data.get("total_conversations", "0")
        calls = account_data.get("total_calls", "0")
        duration = account_data.get("avg_duration", "0")
        transfer_rate = account_data.get("transfer_rate", "0")

        # Format numeric values to consistent format
        # Duration: format to 1 decimal place, remove 's' suffix
        if str(duration).endswith("s"):
            duration = str(duration)[:-1]
        try:
            duration = f"{float(duration):.1f}"
        except (ValueError, TypeError):
            duration = str(duration)

        # Transfer rate: format to 1 decimal place, remove '%' suffix
        if str(transfer_rate).endswith("%"):
            transfer_rate = str(transfer_rate)[:-1]
        try:
            transfer_rate = f"{float(transfer_rate):.1f}"
        except (ValueError, TypeError):
            transfer_rate = str(transfer_rate)

        row = [
            account_name,
            str(users),
            str(conv),
            str(calls),
            duration,
            transfer_rate,
        ]
        data_rows.append(row)

    # Calculate column widths with minimum widths for numeric columns
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in data_rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))

        # Set minimum widths based on column type for engagement table
        if i > 0:  # Skip account name column
            if header in ["Users"]:
                # Users: 6 digits (999,999)
                max_width = max(max_width, 6)
            elif header in ["Conv", "Calls"]:
                # Conversations and Calls: 10 digits (9,999,999,999)
                max_width = max(max_width, 10)
            else:
                # Other numeric columns: keep existing 6 digit width
                max_width = max(max_width, 6)

        col_widths.append(max_width)

    lines = []

    # Header row
    header_line = ""
    for i, header in enumerate(headers):
        if i == 0:
            # Left-align account names
            header_line += header.ljust(col_widths[i])
        else:
            # Right-align numeric columns
            header_line += header.rjust(col_widths[i])
        if i < len(headers) - 1:
            header_line += "  "
    lines.append(header_line)

    # Separator line
    separator = ""
    for i, width in enumerate(col_widths):
        separator += "-" * width
        if i < len(col_widths) - 1:
            separator += "--"
    lines.append(separator)

    # Data rows
    for row in data_rows:
        row_line = ""
        for i, cell in enumerate(row):
            cell_str = str(cell)
            if i == 0:
                # Left-align account names
                row_line += cell_str.ljust(col_widths[i])
            else:
                # Right-align numeric values
                row_line += cell_str.rjust(col_widths[i])
            if i < len(row) - 1:
                row_line += "  "
        lines.append(row_line)

    return "```\n" + "\n".join(lines) + "\n```"


# =============================================================================
# REPORT SECTION BUILDERS
# =============================================================================


def create_engagement_section(unified_accounts: dict, columns: list[str]) -> dict:
    """Create engagement metrics section block with compact table formatting."""
    table_text = create_engagement_table(unified_accounts)
    section_text = "*📈 Account Details*\n\n" + table_text

    return {"type": "section", "text": {"type": "mrkdwn", "text": section_text}}


def build_engagement_summary(totals_summary: dict) -> list[str]:
    """Build engagement summary lines from totals data."""
    summary_lines = []

    if "Active Users" in totals_summary:
        total_users = totals_summary["Active Users"].get("total_active_users", 0)
        summary_lines.append(f"• Active Users: *{total_users}*")

    if "Message Turn Distribution" in totals_summary:
        total_convs = totals_summary["Message Turn Distribution"].get(
            "total_conversations", 0
        )
        avg_turns = totals_summary["Message Turn Distribution"].get(
            "avg_turns_per_conversation", 0
        )
        avg_turns_formatted = safe_float_format(avg_turns, 1)
        summary_lines.append(
            f"• Conversations: *{total_convs}* (Avg {avg_turns_formatted} turns)"
        )

    if "Call Time Metrics" in totals_summary:
        total_calls = totals_summary["Call Time Metrics"].get("total_calls", 0)
        avg_duration = totals_summary["Call Time Metrics"].get("avg_duration", 0)
        avg_duration_formatted = safe_float_format(avg_duration, 1)
        summary_lines.append(
            f"• Calls: *{total_calls}* (Avg {avg_duration_formatted}s)"
        )

    return summary_lines


def build_conversion_section(
    totals_summary: dict, unified_accounts: dict
) -> list[dict]:
    """Build conversion summary section and table blocks."""
    blocks = []

    conversion_summary_lines = []
    if "Conversion Metrics" in totals_summary:
        conv_totals = totals_summary["Conversion Metrics"]

        # Extract conversion metrics
        total_convs_with_orders = conv_totals.get("total_conversations_with_orders", 0)
        total_paid_orders = conv_totals.get("total_paid_orders", 0)
        total_revenue = conv_totals.get("total_subtotal", 0)
        paid_revenue = conv_totals.get("total_paid_total", 0)
        overall_conversion_rate = conv_totals.get("overall_conversion_rate", 0)
        overall_paid_rate = conv_totals.get("overall_paid_rate", 0)

        # Format values safely
        total_revenue_formatted = safe_float_format(total_revenue, 2)
        paid_revenue_formatted = safe_float_format(paid_revenue, 2)
        conversion_rate_formatted = safe_float_format(overall_conversion_rate, 1)
        paid_rate_formatted = safe_float_format(overall_paid_rate, 1)

        conversion_summary_lines.extend(
            [
                f"• Orders: *{total_convs_with_orders}* (Paid: *{total_paid_orders}*)",
                f"• Revenue: *${total_revenue_formatted}* (Paid: *${paid_revenue_formatted}*)",
                f"• Conversion Rate: *{conversion_rate_formatted}%* | Paid Rate: *{paid_rate_formatted}%*",
            ]
        )

    conversion_summary_text = "*💰 Conversion Summary*\n" + "\n".join(
        conversion_summary_lines
    )

    # Add divider, summary, and conversion details
    blocks.extend(
        [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": conversion_summary_text},
            },
            create_conversion_section(unified_accounts),
        ]
    )

    return blocks


def create_conversion_section(unified_accounts: dict) -> dict | None:
    """Create conversion metrics section block using the conversion table format."""
    if not unified_accounts:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*📊 Conversion Details*\n\nNo account data available.",
            },
        }

    table_text = create_conversion_table(unified_accounts)
    section_text = "*📊 Conversion Details*\n\n" + table_text

    return {"type": "section", "text": {"type": "mrkdwn", "text": section_text}}


# =============================================================================
# MAIN REPORT FORMATTING FUNCTIONS
# =============================================================================


def format_unified_report_for_slack(
    reports: list, columns: list[str] | None = None
) -> dict:
    """
    Format unified analytics report into Slack blocks with configurable columns.

    Args:
        reports: List of report objects to merge
        columns: List of column keys to include (defaults to all available)

    Returns:
        dict: Slack blocks structure
    """
    try:
        # Use default columns if none specified
        columns = columns or ENGAGEMENT_COLUMNS

        # Merge all report data
        merged_data = merge_report_data(reports)
        unified_accounts = merged_data["unified_accounts"]
        totals_summary = merged_data["totals_summary"]

        # Build engagement summary
        summary_lines = build_engagement_summary(totals_summary)
        summary_text = "*📊 Engagement Summary*\n" + "\n".join(summary_lines)

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": summary_text}}]

        # Handle case with no account data
        if not unified_accounts:
            logger.warning(
                "[Slackbot] No unified accounts found - showing 'No account data available' message"
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "No account data available."},
                }
            )
            return {"blocks": blocks}

        # Add engagement details section
        logger.info(
            f"[Slackbot] Creating engagement section with {len(unified_accounts)} accounts"
        )
        engagement_section = create_engagement_section(unified_accounts, columns)
        blocks.append(engagement_section)

        # Add conversion section if data exists
        if has_conversion_data(totals_summary, unified_accounts):
            logger.info("[Slackbot] Adding conversion section - conversion data found")
            conversion_blocks = build_conversion_section(
                totals_summary, unified_accounts
            )
            blocks.extend(conversion_blocks)
        else:
            logger.info(
                "[Slackbot] Skipping conversion section - no conversion data found"
            )

        logger.info(f"[Slackbot] Generated {len(blocks)} Slack blocks total")

        return {"blocks": blocks}

    except Exception as e:
        logger.error(f"Error formatting unified report for Slack: {e}")
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Error formatting report data: {str(e)}",
                    },
                }
            ]
        }


# =============================================================================
# SLACK INTEGRATION FUNCTIONS
# =============================================================================


def get_slack_credentials() -> tuple[str, str]:
    """Get Slack bot token and channel from secrets."""
    try:
        bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
    except ValueError as e:
        logger.error(f"[Slackbot] SLACK_BOT_TOKEN not found: {e}")
        raise ValueError("Slack bot token not configured")

    try:
        slack_channel = get_client_secret_with_fallback("SLACK_CHANNEL")
    except ValueError:
        slack_channel = "#test-channel"  # Default fallback

    return bot_token, slack_channel


async def send_report_to_slack(
    slack_channel: str | None = None,
    client: AsyncWebClient | None = None,
    session: Session | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """
    Send a comprehensive analytics report to Slack.

    Args:
        slack_channel: Slack channel to send to (optional, uses secret manager if not provided)
        client: Optional async Slack client to reuse (creates new one if not provided)
        session: Database session for fetching analytics data
        start_date: Start date for the report
        end_date: End date for the report

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

        # Fetch analytics reports
        logger.info(
            f"[Slackbot] Fetching analytics reports from {start_date} to {end_date}"
        )
        reports = await get_reports(
            session, None, start_date, end_date, group_by=["account_id"]
        )
        if not reports.reports:
            logger.warning("[Slackbot] No reports data returned from analytics service")
            return {"status": "error", "message": "No reports data available"}

        # Generate Slack blocks
        logger.info(
            f"[Slackbot] Converting {len(reports.reports)} reports to Slack blocks"
        )
        message_blocks = format_unified_report_for_slack(reports.reports)
        if not message_blocks or "blocks" not in message_blocks:
            logger.error("[Slackbot] Failed to generate valid Slack blocks structure")
            return {"status": "error", "message": "Failed to generate Slack blocks"}

        logger.info(
            f"[Slackbot] Successfully converted {len(reports.reports)} reports to Slack blocks"
        )

        # Send to Slack
        logger.info(f"[Slackbot] Sending report to Slack channel: {target_channel}")
        response = await client.chat_postMessage(
            channel=target_channel, text="Analytics Report", **message_blocks
        )

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

    Args:
        period: The report period ("daily", "weekly", "monthly", "custom")
        message: Slack message object
        client: Slack client object
        custom_dates: Optional tuple of (start_date, end_date) for custom ranges
    """
    try:
        slack_channel = message.get("channel")
        user = message["user"]

        logger.info(
            f"[Slackbot] User {user} requested {period} report in channel {slack_channel}"
        )

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

        # Get database session for conversion data using proper context handling
        session = SyncSessionLocal()
        try:
            result = await send_report_to_slack(
                slack_channel, client, session, start_date, end_date
            )
        finally:
            session.close()

        if result["status"] == "success":
            logger.info(
                f"[Slackbot] {period.capitalize()} report completed successfully"
            )
        else:
            logger.error(
                f"[Slackbot] {period.capitalize()} report failed: {result['message']}"
            )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling {period} request: {e}")


async def handle_custom_date_request(message, client):
    """
    Handle custom date range requests like "From 2024-01-01 to 2024-01-31".

    Args:
        message: Slack message object
        client: Slack client object
    """
    try:
        message_text = message.get("text", "")
        custom_dates = parse_custom_date_range(message_text)

        if custom_dates:
            await handle_report_request("custom", message, client, custom_dates)
        else:
            # Send help message if parsing failed
            slack_channel = message.get("channel")
            help_text = (
                "📅 *Custom Date Range Help*\n\n"
                "Please use the format: `From YYYY-MM-DD to YYYY-MM-DD`\n\n"
                "Example: `From 2024-01-01 to 2024-01-31`"
            )

            await client.chat_postMessage(
                channel=slack_channel, text=help_text, mrkdwn=True
            )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling custom date request: {e}")


# =============================================================================
# SLACK BOT CONFIGURATION
# =============================================================================


def create_slack_app():
    """Create and configure Slack Bolt app with event handlers."""
    try:
        bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
        signing_secret = get_client_secret_with_fallback("SLACK_SIGNING_SECRET")
    except ValueError as e:
        logger.warning(
            f"[Slackbot] Slack credentials not found: {e} - Event handling disabled"
        )
        return None

    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    # Register message handlers for different report periods
    @app.message("daily")
    async def handle_daily_request(message, client):
        """Handle daily report requests."""
        await handle_report_request("daily", message, client)

    @app.message("weekly")
    async def handle_weekly_request(message, client):
        """Handle weekly report requests."""
        await handle_report_request("weekly", message, client)

    @app.message("monthly")
    async def handle_monthly_request(message, client):
        """Handle monthly report requests."""
        await handle_report_request("monthly", message, client)

    @app.message(
        re.compile(r"from\s+\d{4}-\d{2}-\d{2}\s+to\s+\d{4}-\d{2}-\d{2}", re.IGNORECASE)
    )
    async def handle_custom_date_message(message, client):
        """Handle custom date range requests like 'From 2024-01-01 to 2024-01-31'."""
        await handle_custom_date_request(message, client)

    return app


# =============================================================================
# SLACK EVENT HANDLING
# =============================================================================


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
