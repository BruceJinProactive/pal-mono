"""
Slack Report Formatting Module

This module handles formatting of analytics data into professional Slack messages,
including table generation, section building, and report assembly.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from utils.log import logger

# Import access control functions that are needed for formatting
from ._access_control import get_project_display_name

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


# =============================================================================
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
        "Total $",
        "Paid $",
        "Link CVR %",
        "Link Paid %",
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
            elif header in ["Total $", "Paid $"]:
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
    headers = [
        entity_label,
        "Users",
        "Call&Text",
        "Calls",
        "Avg Call Time",
        "Transfer Rate",
        "Res w/o Xfer %",
    ]

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
            transfer_rate_float = float(transfer_rate)
            transfer_rate = f"{transfer_rate_float:.1f}"
            # Calculate resolution rate = 100 - transfer rate
            resolution_rate = f"{100 - transfer_rate_float:.1f}"
        except (ValueError, TypeError):
            transfer_rate = str(transfer_rate)
            resolution_rate = "N/A"

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
            resolution_rate,
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
        # Calculate resolution rate = 100 - transfer rate
        try:
            resolution_rate = 100 - float(transfer_rate)
            resolution_rate_formatted = safe_float_format(resolution_rate, 1)
        except (ValueError, TypeError):
            resolution_rate_formatted = "N/A"
        summary_lines.append(
            f"• Calls: *{total_calls}* (Avg {avg_duration_formatted}s, Transfer Rate {transfer_rate_formatted}%, Resolution without Transfer Rate {resolution_rate_formatted}%)"
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

        # Format values
        total_transaction_formatted = safe_float_format(total_revenue, 2)
        conversion_rate_formatted = safe_float_format(overall_conversion_rate, 1)
        avg_subtotal_formatted = safe_float_format(avg_subtotal, 2)
        paid_orders_display = str(total_paid_orders)
        paid_revenue_formatted = safe_float_format(paid_revenue, 2)
        paid_rate_formatted = safe_float_format(overall_paid_rate, 1)
        avg_paid_total_formatted = safe_float_format(avg_paid_total, 2)

        conversion_summary_lines.extend(
            [
                f"• Orders: *{total_convs_with_orders}* (Paid: *{paid_orders_display}*)",
                f"• Total Order Value: *${total_transaction_formatted}* | Paid Order Total: *${paid_revenue_formatted}*",
                f"• Avg Subtotal: *${avg_subtotal_formatted}* | Avg Paid Total: *${avg_paid_total_formatted}*",
                f"• Checkout Link Conversion Rate: *{conversion_rate_formatted}%* | Payment From Link Rate: *{paid_rate_formatted}%*",
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
