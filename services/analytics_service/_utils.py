from datetime import UTC, datetime, timedelta

from api.schemas.admin.analytics import (
    VALID_CHANNELS,
    AnalyticsReportType,
    AnalyticsResponse,
)


def get_row_value(row, key, default=None):
    """Helper to safely get value from row regardless of result format."""
    # SQLAlchemy Row objects support both attribute and key access
    if hasattr(row, key):  # Named tuple or object with attributes
        return getattr(row, key)
    if hasattr(row, "__getitem__"):  # dict-like or Row object
        try:
            return row[key]
        except (KeyError, IndexError, TypeError):
            pass
    # Try accessing as tuple index if it's a Row object
    if hasattr(row, "_fields") and key in row._fields:
        return row[row._fields.index(key)]
    # Try accessing as dict keys
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    return default


def process_analytics_results_to_dict(
    rows,
    start_date: datetime,
    end_date: datetime,
    report_name: AnalyticsReportType,
) -> AnalyticsResponse:
    """
    Convert analytics query results to nested dictionary format.

    Args:
        rows: Query result rows with date, channel, project_id, and value fields
        start_date: Start date for the analytics calculation
        end_date: End date for the analytics calculation
        report_name: Name of the report type (e.g., DAU, Message Turns, Order)

    Returns:
        AnalyticsResponse: Analytics data with project breakdowns and overall aggregation
    """
    # Convert result to nested dictionary: {date: {project: {channel: count}}}
    analytics_data = {}
    valid_channels = VALID_CHANNELS

    # First, initialize all dates in the range with 0 values
    current_date = start_date.date()
    end_date_only = end_date.date()

    while current_date <= end_date_only:
        date_str = current_date.strftime("%Y-%m-%d")
        analytics_data[date_str] = {}
        current_date += timedelta(days=1)

    value_key = report_name.value

    for _, row in enumerate(rows):
        date_val = get_row_value(row, "date")
        if not date_val:
            continue
        date_str = date_val.strftime("%Y-%m-%d")

        channel_raw = get_row_value(row, "channel")
        channel_name = (channel_raw or "unknown").lower()

        # Only count known channels, ignore unknown ones
        if channel_name in valid_channels:
            # Use project name if available, otherwise fall back to project_id or "unknown"
            project_name = get_row_value(row, "project_name")
            project_id = get_row_value(row, "project_id")

            # Ensure project_key is always a string
            if project_name:
                project_key = str(project_name)
            elif project_id:
                project_key = f"project_{project_id}"
            else:
                project_key = "unknown_project"

            # Initialize project if not exists
            if project_key not in analytics_data[date_str]:
                analytics_data[date_str][project_key] = {
                    channel: 0 for channel in valid_channels
                }

            # Set the value for this project and channel
            raw_value = get_row_value(row, value_key)
            value = raw_value if raw_value is not None else 0

            analytics_data[date_str][project_key][channel_name] = value

            # Update overall aggregation inline (O(1) operation)
            if "overall" not in analytics_data[date_str]:
                analytics_data[date_str]["overall"] = {
                    channel: 0 for channel in valid_channels
                }
            analytics_data[date_str]["overall"][channel_name] += value

    return AnalyticsResponse(analytics_data=analytics_data)


def handle_analytics_date_range(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    max_days: int = 365,
) -> tuple[datetime, datetime]:
    """
    Comprehensive date range handler for analytics operations.

    This function:
    1. Sets default dates (last 7 days) if not provided
    2. Validates date range constraints
    3. Returns formatted date range for logging

    Args:
        start_date: Start date for the range. If None, defaults to 7 days ago
        end_date: End date for the range. If None, defaults to today
        max_days: Maximum allowed days in the range (default: 365)

    Returns:
        tuple[datetime, datetime, str]: (start_date, end_date)

    Raises:
        ValueError: If date range is invalid or exceeds max_days
    """
    # Set default dates if not provided
    if end_date is None or start_date is None:
        # Set end_date to today at 23:59:59
        now = datetime.now(UTC)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Subtract 6 full days to get exactly 7 calendar days
        start_date = end_date - timedelta(days=6)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Validate date range
    if start_date >= end_date:
        raise ValueError("Start date must be before end date")

    # Check if date range exceeds maximum allowed days
    date_diff = end_date - start_date
    if date_diff.days > max_days:
        raise ValueError(f"Date range cannot exceed {max_days} days")

    return start_date, end_date


def normalize_datetime_to_utc(dt: datetime | None) -> datetime | None:
    """
    Convert datetime to UTC timezone.

    Args:
        dt: Datetime to convert. Can be naive (no timezone) or timezone-aware.

    Returns:
        datetime | None: UTC datetime or None if input was None

    Behavior:
        - If dt is None: returns None
        - If dt is naive (no timezone): assumes UTC and adds UTC timezone
        - If dt has timezone: converts to UTC
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        return dt.replace(tzinfo=UTC)
    else:
        # Has timezone - convert to UTC
        return dt.astimezone(UTC)


def build_slack_report_blocks(report: list[dict]) -> list[dict]:
    """Convert report JSON into Slack Block Kit blocks."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Split out TOTAL row
    total = next((r for r in report if r["account_name"].upper() == "TOTAL"), None)
    accounts = [r for r in report if r["account_name"].upper() != "TOTAL"]

    # Header + context
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 Palona • Daily Commerce Report"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Generated on: {now}"}],
        },
        {"type": "divider"},
    ]

    # TOTAL summary
    if total:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*🚀 Summary (TOTAL)*\n"
                        f"• Conversations: *{total['total_conversations']}*\n"
                        f"• Orders: *{total['conversations_with_orders']}*\n"
                        f"• Paid Orders: *{total['conversations_with_paid_orders']}*\n"
                        f"• Checkout CVR: *{total['checkout_conversion_rate']:.2f}%*\n"
                        f"• Paid Rate: *{total['paid_rate']:.2f}%*"
                    ),
                },
            }
        )
        blocks.append({"type": "divider"})

        # Build the table with consistent column spacing
    if accounts:
        # Compute dynamic column widths from values and headers
        name_width = max(
            max(len(r["account_name"]) for r in accounts) + 2, len("Account"), 20
        )

        conv_width = max(
            len("Conv"),
            max(len(str(r["total_conversations"])) for r in accounts),
        )
        orders_width = max(
            len("Orders"),
            max(len(str(r["conversations_with_orders"])) for r in accounts),
        )
        paid_width = max(
            len("Paid"),
            max(len(str(r["conversations_with_paid_orders"])) for r in accounts),
        )

        cvr_values = [f"{r['checkout_conversion_rate']:.1f}" for r in accounts]
        rate_values = [f"{r['paid_rate']:.1f}" for r in accounts]
        cvr_width = max(len("CVR%"), max(len(v) for v in cvr_values))
        rate_width = max(len("Paid%"), max(len(v) for v in rate_values))

        # Define consistent spacing between columns
        col_spacing = "  "  # 2 spaces between columns

        # Build header with dynamic widths and consistent spacing
        header = (
            f"{'Account':<{name_width}}{col_spacing}"
            f"{'Conv':>{conv_width}}{col_spacing}"
            f"{'Orders':>{orders_width}}{col_spacing}"
            f"{'Paid':>{paid_width}}{col_spacing}"
            f"{'CVR%':>{cvr_width}}{col_spacing}"
            f"{'Paid%':>{rate_width}}\n"
        )

        # Calculate total width for separator
        total_width = (
            name_width
            + conv_width
            + orders_width
            + paid_width
            + cvr_width
            + rate_width
            + (len(col_spacing) * 5)
        )
        separator = "-" * total_width + "\n"

        rows = []
        for r in accounts:
            rows.append(
                f"{r['account_name']:<{name_width}}{col_spacing}"
                f"{r['total_conversations']:>{conv_width}}{col_spacing}"
                f"{r['conversations_with_orders']:>{orders_width}}{col_spacing}"
                f"{r['conversations_with_paid_orders']:>{paid_width}}{col_spacing}"
                f"{r['checkout_conversion_rate']:>{cvr_width}.1f}{col_spacing}"
                f"{r['paid_rate']:>{rate_width}.1f}"
            )

        table_text = "```" + header + separator + "\n".join(rows) + "```"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Per Account Breakdown*\n" + table_text,
                },
            }
        )

    # Footer context
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "CVR = orders / conversations · Paid Rate = paid orders / orders",
                }
            ],
        }
    )

    return blocks
