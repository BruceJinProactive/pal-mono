"""
Schedule Calculator Utility

Provides functions to compute execution dates from schedule configurations.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def calculate_next_executions(
    frequency: str,
    start_time: time,
    end_time: time,
    timezone: str,
    days_of_week: list[int] | None = None,
    day_of_month: int | None = None,
    effective_from: date | None = None,
    effective_until: date | None = None,
    count: int = 10,
    from_date: date | None = None,
) -> list[tuple[datetime, datetime]]:
    """
    Calculate the next N execution datetime pairs for a schedule.

    Args:
        frequency: Schedule frequency ('once', 'daily', 'weekly', 'monthly', 'custom')
        start_time: When the routine becomes due
        end_time: Grace period deadline
        timezone: IANA timezone string (e.g., 'America/Los_Angeles')
        days_of_week: For weekly - list of days [0=Sun, 1=Mon, ..., 6=Sat]
        day_of_month: For monthly - day of month (1-31)
        effective_from: Start date for the schedule
        effective_until: End date for the schedule
        count: Number of executions to generate (default 10)
        from_date: Starting date for calculation (default: today in schedule's timezone)

    Returns:
        List of (scheduled_start, scheduled_end) datetime tuples, timezone-aware
    """
    tz = ZoneInfo(timezone)

    # Default from_date is today in the schedule's timezone
    if from_date is None:
        from_date = datetime.now(tz).date()

    # Get execution dates based on frequency
    if frequency == "once":
        execution_dates = _get_execution_dates_once(
            effective_from, effective_until, from_date, count
        )
    elif frequency == "daily":
        execution_dates = _get_execution_dates_daily(
            effective_from, effective_until, from_date, count
        )
    elif frequency == "weekly":
        execution_dates = _get_execution_dates_weekly(
            days_of_week, effective_from, effective_until, from_date, count
        )
    elif frequency == "monthly":
        execution_dates = _get_execution_dates_monthly(
            day_of_month, effective_from, effective_until, from_date, count
        )
    elif frequency == "custom":
        # Custom behaves like daily (runs at start_time each day)
        execution_dates = _get_execution_dates_daily(
            effective_from, effective_until, from_date, count
        )
    else:
        raise ValueError(f"Unknown schedule frequency: {frequency}")

    # Convert dates to datetime pairs
    return [
        _create_execution_window(d, start_time, end_time, tz) for d in execution_dates
    ]


def _create_execution_window(
    exec_date: date,
    start_time: time,
    end_time: time,
    tz: ZoneInfo,
) -> tuple[datetime, datetime]:
    """
    Create a (scheduled_start, scheduled_end) datetime pair.

    Args:
        exec_date: The date of execution
        start_time: When the routine becomes due
        end_time: Grace period deadline
        tz: Timezone for the datetimes

    Returns:
        Tuple of (scheduled_start, scheduled_end) timezone-aware datetimes
    """
    scheduled_start = datetime.combine(exec_date, start_time, tzinfo=tz)

    # Handle overnight windows (end_time < start_time means grace period crosses midnight)
    if end_time < start_time:
        end_date = exec_date + timedelta(days=1)
    else:
        end_date = exec_date
    scheduled_end = datetime.combine(end_date, end_time, tzinfo=tz)

    return (scheduled_start, scheduled_end)


def _get_execution_dates_once(
    effective_from: date | None,
    effective_until: date | None,
    from_date: date,
    count: int,
) -> list[date]:
    """
    For 'once' frequency - returns effective_from date if valid, else empty.

    Args:
        effective_from: Start date for the schedule
        effective_until: End date for the schedule
        from_date: Starting date for calculation
        count: Maximum number of dates to return (ignored, always returns 0 or 1)

    Returns:
        List with at most 1 date
    """
    # 'once' only runs on effective_from date (if set) or from_date
    target_date = effective_from or from_date

    # Check if target_date is not in the past
    if target_date < from_date:
        return []

    # Check effective_until boundary
    if effective_until and target_date > effective_until:
        return []

    return [target_date]


def _get_execution_dates_daily(
    effective_from: date | None,
    effective_until: date | None,
    from_date: date,
    count: int,
) -> list[date]:
    """
    For 'daily' frequency - returns consecutive days starting from from_date.

    Args:
        effective_from: Start date for the schedule
        effective_until: End date for the schedule
        from_date: Starting date for calculation
        count: Maximum number of dates to return

    Returns:
        List of execution dates
    """
    dates: list[date] = []
    current = from_date

    # Start from effective_from if it's in the future
    if effective_from and effective_from > current:
        current = effective_from

    while len(dates) < count:
        # Stop if past effective_until
        if effective_until and current > effective_until:
            break

        dates.append(current)
        current += timedelta(days=1)

    return dates


def _get_execution_dates_weekly(
    days_of_week: list[int] | None,
    effective_from: date | None,
    effective_until: date | None,
    from_date: date,
    count: int,
) -> list[date]:
    """
    For 'weekly' frequency - returns dates matching days_of_week.

    days_of_week format: [0=Sun, 1=Mon, ..., 6=Sat]
    Python weekday(): 0=Mon, ..., 6=Sun

    Args:
        days_of_week: List of days [0=Sun, 1=Mon, ..., 6=Sat]
        effective_from: Start date for the schedule
        effective_until: End date for the schedule
        from_date: Starting date for calculation
        count: Maximum number of dates to return

    Returns:
        List of execution dates
    """
    if not days_of_week:
        return []

    dates: list[date] = []
    current = from_date

    # Start from effective_from if it's in the future
    if effective_from and effective_from > current:
        current = effective_from

    # Convert our days_of_week (0=Sun, 1=Mon, ..., 6=Sat) to Python weekday (0=Mon, ..., 6=Sun)
    target_weekdays = set()
    for dow in days_of_week:
        # Convert: 0=Sun -> 6, 1=Mon -> 0, 2=Tue -> 1, ..., 6=Sat -> 5
        python_weekday = (dow - 1) % 7 if dow > 0 else 6
        target_weekdays.add(python_weekday)

    while len(dates) < count:
        # Stop if past effective_until
        if effective_until and current > effective_until:
            break

        if current.weekday() in target_weekdays:
            dates.append(current)

        current += timedelta(days=1)

    return dates


def _get_execution_dates_monthly(
    day_of_month: int | None,
    effective_from: date | None,
    effective_until: date | None,
    from_date: date,
    count: int,
) -> list[date]:
    """
    For 'monthly' frequency - returns dates matching day_of_month.

    Handles day overflow (e.g., day_of_month=31 for February -> uses Feb 28/29).

    Args:
        day_of_month: Day of month (1-31)
        effective_from: Start date for the schedule
        effective_until: End date for the schedule
        from_date: Starting date for calculation
        count: Maximum number of dates to return

    Returns:
        List of execution dates
    """
    if day_of_month is None:
        return []

    dates: list[date] = []

    # Start from effective_from if it's in the future
    current_date = from_date
    if effective_from and effective_from > current_date:
        current_date = effective_from

    target_day = day_of_month  # 1-31

    # Start with current month
    year, month = current_date.year, current_date.month

    while len(dates) < count:
        # Try to create date with target_day, handle overflow
        candidate = _get_valid_day_in_month(year, month, target_day)

        # Check if candidate is valid (>= current_date and within effective range)
        if candidate >= current_date:
            if effective_until and candidate > effective_until:
                break
            dates.append(candidate)

        # Move to next month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

    return dates


def _get_valid_day_in_month(year: int, month: int, target_day: int) -> date:
    """
    Get a valid date for the given month, clamping to the last day if needed.

    Args:
        year: The year
        month: The month (1-12)
        target_day: The desired day (1-31)

    Returns:
        A valid date, using the last day of the month if target_day exceeds it
    """
    # Try the target day first
    try:
        return date(year, month, target_day)
    except ValueError:
        # Day doesn't exist in this month (e.g., Feb 30)
        # Use the last day of the month
        if month == 12:
            next_month_first = date(year + 1, 1, 1)
        else:
            next_month_first = date(year, month + 1, 1)
        return next_month_first - timedelta(days=1)
