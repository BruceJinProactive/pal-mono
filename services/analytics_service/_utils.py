from datetime import UTC, datetime, timedelta

from api.schemas.admin.analytics import (
    VALID_CHANNELS,
    AnalyticsReportType,
    AnalyticsResponse,
)


def get_row_value(row, key, default=None):
    """Helper to safely get value from row regardless of result format."""
    if hasattr(row, "__getitem__"):  # dict-like or Row object
        try:
            return row[key]
        except (KeyError, IndexError):
            pass
    if hasattr(row, key):  # Named tuple or object with attributes
        return getattr(row, key)
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

    value_key = str(report_name)

    # Then, fill in actual data from the query results
    for row in rows:
        date_val = get_row_value(row, "date")
        if not date_val:
            continue
        date_str = date_val.strftime("%Y-%m-%d")

        channel_raw = get_row_value(row, "channel")
        channel_name = (channel_raw or "unknown").lower()

        pid_val = get_row_value(row, "project_id")
        project_id = str(pid_val) if pid_val else "unknown"

        # Only count known channels, ignore unknown ones
        if channel_name in valid_channels:
            # Use project name if available, otherwise fall back to project_id
            project_name = get_row_value(row, "project_name")
            project_key = project_name or project_id

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
) -> tuple[datetime, datetime, str]:
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
        tuple[datetime, datetime, str]: (start_date, end_date, formatted_range_string)

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

    # Format date range for logging
    formatted_range = f"{start_date.strftime('%Y-%m-%d %H:%M:%S')} to {end_date.strftime('%Y-%m-%d %H:%M:%S')}"

    return start_date, end_date, formatted_range
