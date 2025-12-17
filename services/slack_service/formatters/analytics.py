"""
Analytics Report Formatting for Slack

This module handles all analytics-specific formatting for Slack reports including:
- Date range parsing and timezone handling
- Report data merging and processing
- Table creation (engagement, conversion)
- Section builders for Slack blocks
- Main report formatting function

All analytics formatting logic is centralized here to keep it separate
from generic Slack service infrastructure.
"""

import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from services.analytics_service._utils import normalize_datetime_to_utc
from utils.log import logger

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


# =============================================================================
# DATE UTILITY FUNCTIONS
# =============================================================================


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


def get_project_display_name(
    project_name: str,
    session: Session | None = None,
    account_id: uuid.UUID | None = None,
) -> str:
    """
    Get project display_name from database using project_name and account_id.

    Uses service layer functions to query the database.

    Args:
        project_name: Project name string
        session: Database session (optional)
        account_id: Account UUID to help identify the project (optional but recommended)

    Returns:
        Project display_name if found, otherwise project_name
    """
    if not session:
        return project_name

    try:
        from services import account_service, project_service

        # If account_id provided, filter projects by account
        if account_id:
            # Get account by ID first
            account = account_service.get_account_by_id(session, account_id)
            if account:
                # Get all projects for this account
                projects = project_service.get_projects_by_account_id(
                    session, account.id
                )
                # Find the specific project by name
                for project in projects:
                    if project.name == project_name and project.display_name:
                        return project.display_name
        else:
            # No account_id provided, just search by project name
            project = project_service.get_project_by_name(session, project_name)
            if project and project.display_name:
                return project.display_name

        # Fallback to project_name if display_name not set or project not found
        return project_name

    except Exception as e:
        logger.warning(
            f"[Slackbot] Error looking up project display_name for project='{project_name}', account='{account_id}': {e}"
        )
        return project_name


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
        from services import integration_service

        # Use integration service instead of direct database query
        integrations = integration_service.get_integrations_by_account_id(
            session, account_id
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
            display_name = get_project_display_name(name, session, account_id)

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
        logger.info(
            f"[Slackbot DEBUG] Checking integrations for account_id={account_id_filter}, session={'present' if session else 'None'}"
        )
        integrations = get_account_integrations(account_id_filter, session)
        has_adora_integration = "adora" in integrations
        logger.info(
            f"[Slackbot] Conversion summary: has_adora={has_adora_integration}, integrations={integrations}, account_id={account_id_filter}"
        )
    else:
        logger.warning(
            f"[Slackbot DEBUG] Skipping integration check: account_id_filter={account_id_filter}, session={'present' if session else 'None'}"
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
    account_name: str | None = None,
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
