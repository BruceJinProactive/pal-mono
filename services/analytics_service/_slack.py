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
import uuid
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


def get_account_timezone(session: Session, account_name: str) -> str:
    """
    Get the timezone for an account by looking up its first project's timezone.

    Args:
        session: Database session
        account_name: Account name to look up

    Returns:
        str: Timezone ID (e.g., 'America/Los_Angeles'), defaults to 'America/Los_Angeles' if not found
    """
    try:
        from db.tables.accounts import Account

        # Query account by name and join with projects to get timezone
        account = (
            session.query(Account).filter(Account.name.ilike(account_name)).first()
        )

        if account and account.projects:
            # Use the first project's timezone
            timezone = account.projects[0].timezone
            if timezone:
                logger.info(
                    f"[Slackbot] Found timezone '{timezone}' for account '{account_name}'"
                )
                return timezone

        logger.warning(
            f"[Slackbot] No timezone found for account '{account_name}', using default 'America/Los_Angeles'"
        )
        return "America/Los_Angeles"

    except Exception as e:
        logger.error(
            f"[Slackbot] Error looking up timezone for account '{account_name}': {e}"
        )
        return "America/Los_Angeles"


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


def get_date_range_for_hours(
    hours: int, session: Session | None = None, account_name: str | None = None
) -> tuple[datetime, datetime]:
    """
    Generate start_date and end_date for custom hour range.

    Args:
        hours: Number of hours to look back
        session: Database session (optional) - used to look up account timezone
        account_name: Account name (optional) - if provided, dates are calculated in account's timezone

    Returns:
        tuple[datetime, datetime]: (start_date, end_date) in UTC
    """
    # Get account timezone if available, otherwise default to PST
    timezone_id = None
    if session and account_name:
        timezone_id = get_account_timezone(session, account_name)

    if not timezone_id:
        # Default to PST when no account specified or timezone not found
        timezone_id = "America/Los_Angeles"

    # Get current time in the timezone (account's or PST)
    from zoneinfo import ZoneInfo

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


def get_date_range_for_period(
    period: str, session: Session | None = None, account_name: str | None = None
) -> tuple[datetime, datetime]:
    """
    Generate start_date and end_date for different reporting periods.

    Args:
        period: "daily", "weekly", or "monthly"
        session: Database session (optional) - used to look up account timezone
        account_name: Account name (optional) - if provided, dates are calculated in account's timezone

    Returns:
        tuple[datetime, datetime]: (start_date, end_date) in UTC
    """
    # Get account timezone if available, otherwise default to PST
    timezone_id = None
    if session and account_name:
        timezone_id = get_account_timezone(session, account_name)

    if not timezone_id:
        # Default to PST when no account specified or timezone not found
        timezone_id = "America/Los_Angeles"

    # Get current time in the timezone (account's or PST)
    from zoneinfo import ZoneInfo

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


def get_project_display_name(project_id: str, session: Session | None = None) -> str:
    """
    Get project display_name from database, fallback to project_id if not found.

    Args:
        project_id: Project UUID string
        session: Database session (optional)

    Returns:
        Project display_name if found, otherwise project_id
    """
    if not session:
        return project_id

    try:
        from db.tables.projects import Project

        project = session.query(Project).filter(Project.id == project_id).first()

        if project and project.display_name:
            return project.display_name

        # Fallback to project_id if display_name not set
        return project_id

    except Exception as e:
        logger.warning(
            f"[Slackbot] Error looking up project display_name for {project_id}: {e}"
        )
        return project_id


def get_account_integrations(
    account_id: uuid.UUID, session: Session | None = None
) -> list[str]:
    """
    Get integrations for an account as a list of provider names.

    Args:
        account_id: Account UUID
        session: Database session (optional)

    Returns:
        List of integration provider names (e.g., ["toast", "opentable"]) or empty list
    """
    if not session:
        logger.warning(
            f"[Slackbot] get_account_integrations called with no session for account {account_id}"
        )
        return []

    try:
        from db.tables.integration import Integration

        integrations = (
            session.query(Integration)
            .filter(Integration.account_id == account_id)
            .all()
        )

        if not integrations:
            logger.info(f"[Slackbot] No integrations found for account {account_id}")
            return []

        # Return list of provider names (lowercase)
        provider_list = [integration.provider.value for integration in integrations]
        logger.info(
            f"[Slackbot] Found {len(provider_list)} integrations for account {account_id}: {provider_list}"
        )
        return provider_list

    except Exception as e:
        logger.warning(
            f"[Slackbot] Error looking up integrations for account {account_id}: {e}",
            exc_info=True,
        )
        return []


def truncate_account_name(account_name: str, max_length: int = 15) -> str:
    """
    Truncate account name for table display while keeping it readable.

    Args:
        account_name: Full account name
        max_length: Maximum length for display (default 15, including "...")

    Returns:
        Truncated account name with ellipsis if needed
    """
    if len(account_name) <= max_length:
        return account_name

    # Try to truncate at word boundaries first (for hyphenated names)
    if "-" in account_name:
        words = account_name.split("-")
        truncated = words[0]
        for word in words[1:]:
            if len(truncated + "-" + word) <= max_length - 3:  # Leave room for "..."
                truncated += "-" + word
            else:
                break
        if truncated != account_name:
            return truncated + "..."

    # Fallback: simple truncation
    return account_name[: max_length - 3] + "..."


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
        row = [truncate_account_name(account_name)]
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


def _create_conversion_table_generic(
    unified_data: dict,
    entity_label: str = "Account",
    session: Session | None = None,
    account_id: uuid.UUID | None = None,
) -> str:
    """Generic conversion table creator for both accounts and projects."""
    if not unified_data:
        return f"No {entity_label.lower()} data available."

    # Note: Adora integration check removed from table generation
    # N/A values now only apply to summary section, not the table

    # Headers with conversation value and paid value
    headers = [
        entity_label,
        "Call&Text",
        "Orders",
        "Paid",
        "Subtotal",
        "Paidtotal",
        "CVR%",
        "Paid%",
    ]

    # First filter out entries with 0 orders and sort by orders (high to low)
    filtered_data = []
    for name, data in unified_data.items():
        orders = data.get("conversations_with_orders", "0")
        try:
            orders_int = int(orders)
            if orders_int > 0:
                filtered_data.append((name, data, orders_int))
        except (ValueError, TypeError):
            continue

    # Sort by orders (high to low) and limit to first 15
    filtered_data.sort(key=lambda x: x[2], reverse=True)
    limited_data = filtered_data[:15]

    # Build data rows
    data_rows = []
    for name, item_data, _ in limited_data:
        conv = item_data.get("total_conversations", "0")
        orders = item_data.get("conversations_with_orders", "0")

        # Always show actual values in the table (no N/A)
        paid = item_data.get("paid_orders", "0")
        paid_value = safe_float_format(item_data.get("paid_total", 0), 1)
        paid_rate = safe_float_format(item_data.get("paid_rate", 0), 1)

        conv_value = safe_float_format(item_data.get("total_subtotal", 0), 1)
        cvr = safe_float_format(item_data.get("conversion_rate", 0), 1)

        # For projects, use display_name if available
        display_name = name
        if entity_label == "Project" and session:
            display_name = get_project_display_name(name, session)

        row = [
            truncate_account_name(display_name),
            str(conv),
            str(orders),
            str(paid),
            conv_value,
            paid_value,
            cvr,
            paid_rate,
        ]
        data_rows.append(row)

    # Handle case where no entries have orders
    if not data_rows:
        return f"No {entity_label.lower()}s with orders found."

    # Calculate column widths with minimum widths for numeric columns
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in data_rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))

        # Set minimum widths based on column type for conversion table
        if i > 0:  # Skip entity name column
            if header in ["Call&Text"]:
                # Call&Text: 10 digits (9,999,999,999)
                max_width = max(max_width, 10)
            elif header in ["Subtotal", "Paidtotal"]:
                # Revenue columns: wider for currency values (e.g., "123,456.7")
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
            # Left-align entity names
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
                # Left-align entity names
                row_line += cell_str.ljust(col_widths[i])
            else:
                # Right-align numeric values
                row_line += cell_str.rjust(col_widths[i])
            if i < len(row) - 1:
                row_line += "  "
        lines.append(row_line)

    return "```\n" + "\n".join(lines) + "\n```"


def create_project_conversion_table(
    unified_projects: dict,
    session: Session | None = None,
    account_id: uuid.UUID | None = None,
) -> str:
    """Create a conversion table for projects with conversation value and paid value columns, filtering out projects with 0 orders."""
    return _create_conversion_table_generic(
        unified_projects, "Project", session, account_id
    )


def create_conversion_table(unified_accounts: dict) -> str:
    """Create a conversion table with conversation value and paid value columns, filtering out accounts with 0 orders."""
    return _create_conversion_table_generic(unified_accounts, "Account")


def _create_engagement_table_generic(
    unified_data: dict, entity_label: str = "Account", session: Session | None = None
) -> str:
    """Generic engagement table creator for both accounts and projects."""
    if not unified_data:
        return f"No {entity_label.lower()} data available."

    # Headers with key engagement metrics
    headers = [entity_label, "Users", "Call&Text", "Calls", "Dur", "Xfer%"]

    # Build data rows - limit to first 15 entries
    data_rows = []
    count = 0
    for name, item_data in unified_data.items():
        if count >= 15:
            break
        count += 1
        users = item_data.get("active_users", "0")
        conv = item_data.get("total_conversations", "0")
        calls = item_data.get("total_calls", "0")
        duration = item_data.get("avg_duration", "0")
        transfer_rate = item_data.get("transfer_rate", "0")

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

        # For projects, use display_name if available
        display_name = name
        if entity_label == "Project" and session:
            display_name = get_project_display_name(name, session)

        row = [
            truncate_account_name(display_name),
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
        if i > 0:  # Skip entity name column
            if header in ["Users"]:
                # Users: 6 digits (999,999)
                max_width = max(max_width, 6)
            elif header in ["Call&Text", "Calls"]:
                # Call&Text and Calls: 10 digits (9,999,999,999)
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
            # Left-align entity names
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
                # Left-align entity names
                row_line += cell_str.ljust(col_widths[i])
            else:
                # Right-align numeric values
                row_line += cell_str.rjust(col_widths[i])
            if i < len(row) - 1:
                row_line += "  "
        lines.append(row_line)

    return "```\n" + "\n".join(lines) + "\n```"


def create_project_engagement_table(
    unified_projects: dict, session: Session | None = None
) -> str:
    """Create an engagement table for projects with key metrics including call quality."""
    return _create_engagement_table_generic(unified_projects, "Project", session)


def create_engagement_table(unified_accounts: dict) -> str:
    """Create an engagement table with key metrics including call quality."""
    return _create_engagement_table_generic(unified_accounts, "Account")


# =============================================================================
# REPORT SECTION BUILDERS
# =============================================================================


def _create_engagement_section_generic(
    unified_data: dict,
    columns: list[str],
    entity_label: str = "Account",
    session: Session | None = None,
) -> dict:
    """Generic engagement section creator for both accounts and projects."""
    table_text = _create_engagement_table_generic(unified_data, entity_label, session)
    section_text = f"*📈 {entity_label} Details*\n\n" + table_text

    return {"type": "section", "text": {"type": "mrkdwn", "text": section_text}}


def create_project_engagement_section(
    unified_projects: dict, columns: list[str], session: Session | None = None
) -> dict:
    """Create engagement metrics section block for projects with compact table formatting."""
    return _create_engagement_section_generic(
        unified_projects, columns, "Project", session
    )


def create_engagement_section(unified_accounts: dict, columns: list[str]) -> dict:
    """Create engagement metrics section block with compact table formatting."""
    return _create_engagement_section_generic(unified_accounts, columns, "Account")


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
        summary_lines.append(f"• Call&Text: *{total_convs}*")

    if "Call Time Metrics" in totals_summary:
        total_calls = totals_summary["Call Time Metrics"].get("total_calls", 0)
        avg_duration = totals_summary["Call Time Metrics"].get("avg_duration", 0)
        transfer_rate = totals_summary["Call Time Metrics"].get(
            "overall_transfer_rate", 0
        )
        avg_duration_formatted = safe_float_format(avg_duration, 1)
        transfer_rate_formatted = safe_float_format(transfer_rate, 1)
        summary_lines.append(
            f"• Calls: *{total_calls}* (Avg {avg_duration_formatted}s, Transfer Rate {transfer_rate_formatted}%)"
        )

    return summary_lines


def build_conversion_section(
    totals_summary: dict,
    unified_accounts: dict,
    account_id_filter: uuid.UUID | None = None,
    account_name: str | None = None,
    session: Session | None = None,
) -> list[dict]:
    """Build conversion summary section and table blocks."""
    blocks = []

    # Check if account has Adora integration (for summary N/A display)
    has_adora_integration = False
    if account_id_filter and session:
        integrations = get_account_integrations(account_id_filter, session)
        has_adora_integration = "adora" in integrations
        logger.info(
            f"[Slackbot] Conversion summary: has_adora={has_adora_integration}, integrations={integrations}"
        )

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

        # Calculate averages
        avg_subtotal = (
            total_revenue / total_convs_with_orders
            if total_convs_with_orders > 0
            else 0
        )
        avg_paid_total = (
            paid_revenue / total_paid_orders if total_paid_orders > 0 else 0
        )

        # Format values - use N/A for paid metrics if Adora integration exists
        total_transaction_formatted = safe_float_format(total_revenue, 2)
        conversion_rate_formatted = safe_float_format(overall_conversion_rate, 1)
        avg_subtotal_formatted = safe_float_format(avg_subtotal, 2)

        if has_adora_integration:
            # Show N/A for paid metrics in summary
            paid_orders_display = "N/A"
            paid_revenue_formatted = "N/A"
            paid_rate_formatted = "N/A"
            avg_paid_total_formatted = "N/A"
        else:
            # Show actual values
            paid_orders_display = str(total_paid_orders)
            paid_revenue_formatted = safe_float_format(paid_revenue, 2)
            paid_rate_formatted = safe_float_format(overall_paid_rate, 1)
            avg_paid_total_formatted = safe_float_format(avg_paid_total, 2)

        conversion_summary_lines.extend(
            [
                f"• Orders: *{total_convs_with_orders}* (Paid: *{paid_orders_display}*)",
                f"• Subtotal Value: *${total_transaction_formatted}* | Paid Total: *${paid_revenue_formatted}*",
                f"• Avg Subtotal: *${avg_subtotal_formatted}* | Avg Paid Total: *${avg_paid_total_formatted}*",
                f"• Checkout Rate: *{conversion_rate_formatted}%* | Paid Rate: *{paid_rate_formatted}%*",
            ]
        )

    # For single-account reports, skip the conversion summary header (already covered by main header)
    # For multi-account reports, show separate "Conversion Summary" header
    if account_id_filter is None:
        conversion_summary_text = "*💰 Conversion Summary*\n" + "\n".join(
            conversion_summary_lines
        )
        # Add divider and summary for multi-account reports
        blocks.extend(
            [
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": conversion_summary_text},
                },
            ]
        )
    else:
        # Single account - no header, no divider, just the metrics
        conversion_summary_text = "\n".join(conversion_summary_lines)
        # Add summary without divider for single-account reports
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": conversion_summary_text},
            }
        )

    # Add conversion table
    # For multi-account reports: show account-level table
    # For single-account reports: show project-level table
    if account_id_filter is None:
        blocks.append(create_conversion_section(unified_accounts))
    else:
        logger.info(
            f"[Slackbot] Creating project conversion table for single account (account_id: {account_id_filter})"
        )
        # Use unified_accounts as unified_projects since we grouped by project_id
        blocks.append(
            create_project_conversion_section(
                unified_accounts, session, account_id_filter
            )
        )

    return blocks


def _create_conversion_section_generic(
    unified_data: dict,
    entity_label: str = "Account",
    session: Session | None = None,
    account_id: uuid.UUID | None = None,
) -> dict | None:
    """Generic conversion section creator for both accounts and projects."""
    if not unified_data:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📊 Conversion Details*\n\nNo {entity_label.lower()} data available.",
            },
        }

    table_text = _create_conversion_table_generic(
        unified_data, entity_label, session, account_id
    )
    section_text = "*📊 Conversion Details*\n\n" + table_text

    return {"type": "section", "text": {"type": "mrkdwn", "text": section_text}}


def create_project_conversion_section(
    unified_projects: dict,
    session: Session | None = None,
    account_id: uuid.UUID | None = None,
) -> dict | None:
    """Create conversion metrics section block for projects using the conversion table format."""
    return _create_conversion_section_generic(
        unified_projects, "Project", session, account_id
    )


def create_conversion_section(unified_accounts: dict) -> dict | None:
    """Create conversion metrics section block using the conversion table format."""
    return _create_conversion_section_generic(unified_accounts, "Account")


# =============================================================================
# MAIN REPORT FORMATTING FUNCTIONS
# =============================================================================


def format_unified_report_for_slack(
    reports: list,
    columns: list[str] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    show_time: bool = False,
    timezone_id: str | None = None,
    timezone_name: str | None = None,
    account_id_filter: uuid.UUID | None = None,
    account_name: str | None = None,
    session: Session | None = None,
) -> dict:
    """
    Format unified analytics report into Slack blocks with configurable columns.

    Args:
        reports: List of report objects to merge
        columns: List of column keys to include (defaults to all available)
        start_date: Start date of the report period (in UTC)
        end_date: End date of the report period (in UTC)
        show_time: If True, show full datetime with time and timezone (for hourly reports)
        timezone_id: Timezone ID to convert UTC times to local time (e.g., 'America/New_York')
        timezone_name: Timezone abbreviation to display (e.g., 'EST', 'PST')

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

        # Create date range header if dates are provided
        blocks = []
        if start_date and end_date:
            if show_time:
                # Format with time and timezone for hourly reports
                if timezone_id:
                    # Convert UTC times to local timezone before formatting
                    from zoneinfo import ZoneInfo

                    tz = ZoneInfo(timezone_id)
                    start_local = start_date.astimezone(tz)
                    end_local = end_date.astimezone(tz)

                    start_formatted = start_local.strftime("%Y-%m-%d %I:%M %p")
                    end_formatted = end_local.strftime("%Y-%m-%d %I:%M %p")

                    # Use timezone_name if provided, otherwise use timezone abbreviation
                    tz_label = (
                        timezone_name if timezone_name else start_local.strftime("%Z")
                    )
                    date_range_text = f"*📅 Report Period: {start_formatted} to {end_formatted} {tz_label}*"
                else:
                    # Show in UTC
                    start_formatted = start_date.strftime("%Y-%m-%d %I:%M %p UTC")
                    end_formatted = end_date.strftime("%Y-%m-%d %I:%M %p UTC")
                    date_range_text = (
                        f"*📅 Report Period: {start_formatted} to {end_formatted}*"
                    )
            else:
                # Format with date only for daily/weekly/monthly reports
                start_formatted = start_date.strftime("%Y-%m-%d")
                end_formatted = end_date.strftime("%Y-%m-%d")
                date_range_text = (
                    f"*📅 Report Period: {start_formatted} to {end_formatted}*"
                )
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": date_range_text}}
            )

        # Build engagement summary
        summary_lines = build_engagement_summary(totals_summary)

        # Use account-specific header for single-account reports
        if account_id_filter is not None and account_name:
            summary_header = f"*📊 {account_name.title()}'s Report*"
        else:
            summary_header = "*📊 Engagement Summary*"

        summary_text = summary_header + "\n" + "\n".join(summary_lines)

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": summary_text}}
        )

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
        # For multi-account reports: show account-level table
        # For single-account reports: show project-level table
        if account_id_filter is None:
            logger.info(
                f"[Slackbot] Creating engagement section with {len(unified_accounts)} accounts"
            )
            engagement_section = create_engagement_section(unified_accounts, columns)
            blocks.append(engagement_section)
        else:
            logger.info(
                f"[Slackbot] Creating project engagement table for single account (account_id: {account_id_filter})"
            )
            # Use unified_accounts as unified_projects since we grouped by project_id
            project_engagement_section = create_project_engagement_section(
                unified_accounts, columns, session
            )
            blocks.append(project_engagement_section)

        # Add conversion section if data exists
        if has_conversion_data(totals_summary, unified_accounts):
            logger.info("[Slackbot] Adding conversion section - conversion data found")
            conversion_blocks = build_conversion_section(
                totals_summary,
                unified_accounts,
                account_id_filter,
                account_name,
                session,
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

# Internal channels that can see all account data
INTERNAL_CHANNELS = {
    "agent-performance",
    "test-channel",
    "#agent-performance",
    "#test-channel",
}


def get_account_id_by_name(account_name: str, session: Session) -> uuid.UUID | None:
    """
    Look up account ID by account name from database.

    Args:
        account_name: Account name to look up
        session: Database session

    Returns:
        uuid.UUID | None: Account ID if found, None otherwise
    """
    try:
        from db.tables.accounts import Account

        # Query account by name (case-insensitive)
        account = (
            session.query(Account).filter(Account.name.ilike(account_name)).first()
        )

        if account:
            logger.info(
                f"[Slackbot] Found account '{account.name}' with ID {account.id}"
            )
            return account.id
        else:
            logger.warning(f"[Slackbot] No account found with name '{account_name}'")
            return None

    except Exception as e:
        logger.error(
            f"[Slackbot] Error looking up account by name '{account_name}': {e}"
        )
        return None


def extract_account_from_channel(channel_display_name: str) -> str | None:
    """
    Extract account name from client channel names.

    For channels in format "#client-account-name", extracts "account-name".

    Args:
        channel_display_name: Channel name (e.g., "#client-acme-restaurant")

    Returns:
        str | None: Account name if channel is a client channel, None otherwise
    """
    normalized = channel_display_name.strip().lstrip("#").lower()
    if normalized.startswith("client-"):
        # Extract everything after "client-"
        account_name = normalized[7:]  # len("client-") = 7
        return account_name if account_name else None
    return None


def determine_account_filter(
    channel: str,
    session: Session,
    account_name: str | None = None,
    channel_display_name: str | None = None,
) -> tuple[uuid.UUID | None, str | None]:
    """
    Determine which account(s) to show based on channel and optional account name.

    For client channels (starting with "client-"):
    - Extracts account name from channel (e.g., #client-acme-restaurant -> acme-restaurant)
    - If user provides account name via "for", validates first 3 characters match
    - If no account name provided, auto-uses channel's account

    Priority:
    1. If in internal channel -> show all accounts (return None)
    2. If channel starts with "client-" -> extract account from channel name
       a. If account_name provided -> verify first 3 chars match channel account
       b. If no account_name -> auto-use channel's account
    3. Otherwise -> show all accounts (return None)

    Args:
        channel: Slack channel ID or name
        session: Database session
        account_name: Optional account name from message (e.g., "daily for acme")
        channel_display_name: Optional human-readable channel name for logging

    Returns:
        tuple[uuid.UUID | None, str | None]: (account_id, error_message)
        - (account_id, None) if successful
        - (None, None) if showing all accounts (internal channel)
        - (None, error_message) if error occurred
    """
    # Use display name for logging if available, otherwise use channel ID
    display_name = channel_display_name or channel

    # Priority 1: Check if it's an internal channel (can see all accounts)
    normalized_channel = channel.strip().lstrip("#")
    if normalized_channel in INTERNAL_CHANNELS or channel in INTERNAL_CHANNELS:
        logger.info(
            f"[Slackbot] Channel '{display_name}' is internal - showing all accounts"
        )
        return None, None

    # Priority 2: Check if channel is a client channel (starts with "client-")
    channel_account_name = extract_account_from_channel(display_name)
    if channel_account_name:
        # This is a client channel
        if not account_name:
            # No account specified - require user to specify
            error_msg = (
                f"Please specify the account name using the format: `daily for account-name`\n"
                f"This channel is for accounts starting with '{channel_account_name[:3]}'."
            )
            logger.warning(
                f"[Slackbot] Channel '{display_name}' is a client channel and no account specified - account name required"
            )
            return None, error_msg

        # User specified account name - verify first 3 chars match
        if len(account_name) < 3 or len(channel_account_name) < 3:
            error_msg = f"Account name too short for validation. Channel account: '{channel_account_name}'"
            logger.warning(f"[Slackbot] {error_msg}")
            return None, error_msg

        account_prefix = account_name[:3].lower()
        channel_prefix = channel_account_name[:3].lower()

        if account_prefix != channel_prefix:
            error_msg = (
                f"❌ Account '{account_name}' is not matched with this channel. "
                f"This channel is for accounts starting with '{channel_prefix}'."
            )
            logger.warning(f"[Slackbot] Account name mismatch: {error_msg}")
            return None, error_msg

        # First 3 chars match - proceed with user-specified account
        logger.info(
            f"[Slackbot] Account name '{account_name}' matches channel '{display_name}'"
        )

        # Look up account ID
        account_id = get_account_id_by_name(account_name, session)
        if account_id:
            return account_id, None
        else:
            error_msg = f"Cannot find account info for '{account_name}'. Please check the account name and try again."
            logger.warning(f"[Slackbot] Account '{account_name}' not found in database")
            return None, error_msg

    # Priority 3: Not internal, not client channel - check if account name provided
    if account_name:
        # Allow explicit account filtering in non-client channels
        account_id = get_account_id_by_name(account_name, session)
        if account_id:
            logger.info(
                f"[Slackbot] Using explicit account filter '{account_name}' in channel '{display_name}'"
            )
            return account_id, None
        else:
            error_msg = f"Cannot find account info for '{account_name}'. Please check the account name and try again."
            logger.warning(f"[Slackbot] Account '{account_name}' not found")
            return None, error_msg

    # Priority 4: For other channels without account name, allow showing all accounts
    logger.info(f"[Slackbot] Channel '{display_name}' - showing all accounts")
    return None, None


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

    async def process_message(event, client):
        """Shared logic to process messages from both mentions and DMs."""
        message_text = event.get("text", "").lower()

        # Check for daily report
        if "daily" in message_text:
            await handle_report_request("daily", event, client)
        # Check for weekly report
        elif "weekly" in message_text:
            await handle_report_request("weekly", event, client)
        # Check for monthly report
        elif "monthly" in message_text:
            await handle_report_request("monthly", event, client)
        # Check for last X hours
        elif re.search(r"last\s+\d+\s+hours?", message_text, re.IGNORECASE):
            await handle_last_hours_request(event, client)
        # Check for custom date range (with optional time: HH:MM)
        elif re.search(
            r"from\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?\s+to\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?",
            message_text,
            re.IGNORECASE,
        ):
            await handle_custom_date_request(event, client)
        else:
            # Unknown command - send simple error message
            channel = event.get("channel")
            error_text = "Please try again."
            await client.chat_postMessage(channel=channel, text=error_text, mrkdwn=True)

    # Register app_mention handler to only respond when bot is @mentioned
    @app.event("app_mention")
    async def handle_app_mention(event, client):
        """Handle all app mentions and route to appropriate handler."""
        await process_message(event, client)

    # Register message handler to respond to direct messages only
    @app.event("message")
    async def handle_message(event, client, say):
        """Handle direct messages to the bot only (not public channels)."""
        # Only respond to direct messages, not public channel messages
        # In DMs, channel_type is "im" (instant message)
        # In public channels, channel_type is "channel"
        # In private channels, channel_type is "group"
        channel_type = event.get("channel_type")

        # Only process if it's a direct message AND not from a bot
        if (
            channel_type == "im"
            and event.get("subtype") is None
            and event.get("bot_id") is None
        ):
            await process_message(event, client)

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
