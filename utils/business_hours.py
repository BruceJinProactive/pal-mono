"""Check whether a store is open at a given instant from its business hours.

Operates on the Google Places hours shape (``regular_hours`` / ``special_hours``).
``is_within_business_hours`` is the entry point; the rest are its helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from utils.log import logger

DEFAULT_TIMEZONE = "America/Los_Angeles"


@dataclass
class BusinessHoursCheckResult:
    """Result of business hours check."""

    is_open: bool
    reason: str
    period_info: dict | None = None


def parse_google_time(time_str: str) -> time:
    """
    Parse Google Places time format "HHMM" to time object.

    Args:
        time_str: Time in "HHMM" format (e.g., "0900", "2200")

    Returns:
        time object
    """
    if not time_str or len(time_str) != 4:
        logger.warning(
            f"Invalid time format '{time_str}', defaulting to 00:00",
            extra={"invalid_time": time_str},
        )
        return time(0, 0)
    try:
        hour = int(time_str[:2])
        minute = int(time_str[2:])
        return time(hour, minute)
    except (ValueError, TypeError):
        logger.warning(
            f"Failed to parse time '{time_str}', defaulting to 00:00",
            extra={"invalid_time": time_str},
        )
        return time(0, 0)


def _check_special_hours(
    check_date: date,
    check_time: time,
    special_hours: list[dict],
) -> BusinessHoursCheckResult | None:
    """
    Check if date has special hours (holidays, etc.).

    Handles overnight periods that span midnight (e.g., 22:00 to 02:00).
    For overnight periods, checks both:
    - Opening portion on the open day (after open time)
    - Closing portion on the next day (before close time)

    Args:
        check_date: Date to check
        check_time: Time to check
        special_hours: List of special hours from Google Places API

    Returns:
        BusinessHoursCheckResult if special hours apply, None otherwise
    """
    from datetime import timedelta

    for special in special_hours:
        special_date_str = special.get("date")
        if not special_date_str:
            continue

        try:
            # Parse date in YYYY-MM-DD format
            special_date = date.fromisoformat(special_date_str)
        except (ValueError, TypeError):
            continue

        # Check if this special date matches today or yesterday (for overnight periods)
        is_today = special_date == check_date
        is_yesterday = special_date == check_date - timedelta(days=1)

        if not is_today and not is_yesterday:
            continue

        # Found potentially matching special date
        periods = special.get("periods", [])

        # If no periods defined for special day, it's closed (only applies to today)
        if not periods and is_today:
            return BusinessHoursCheckResult(
                is_open=False,
                reason="special_closure",
                period_info={"date": special_date_str, "closed": True},
            )

        # Check if current time is within any special period
        for period in periods:
            open_info = period.get("open", {})
            close_info = period.get("close", {})

            open_time = parse_google_time(open_info.get("time", "0000"))
            close_time = parse_google_time(close_info.get("time", "2359"))

            # Check for overnight period (close time is earlier than open time)
            is_overnight = open_time > close_time

            if is_overnight:
                # Overnight period: e.g., 22:00 to 02:00
                if is_today:
                    # We're on the opening day - check if we're after open time
                    if check_time >= open_time:
                        return BusinessHoursCheckResult(
                            is_open=True,
                            reason="within_special_hours_overnight",
                            period_info={
                                "date": special_date_str,
                                "open": open_time.strftime("%H:%M"),
                                "close": close_time.strftime("%H:%M"),
                                "overnight": True,
                            },
                        )
                elif is_yesterday:
                    # We're on the closing day (day after the special date)
                    # Check if we're before close time
                    if check_time <= close_time:
                        return BusinessHoursCheckResult(
                            is_open=True,
                            reason="within_special_hours_overnight",
                            period_info={
                                "date": special_date_str,
                                "open": open_time.strftime("%H:%M"),
                                "close": close_time.strftime("%H:%M"),
                                "overnight": True,
                            },
                        )
            elif is_today:
                # Same-day period: standard check
                if open_time <= check_time <= close_time:
                    return BusinessHoursCheckResult(
                        is_open=True,
                        reason="within_special_hours",
                        period_info={
                            "date": special_date_str,
                            "open": open_time.strftime("%H:%M"),
                            "close": close_time.strftime("%H:%M"),
                        },
                    )

        # Special hours defined for today but not currently within any period
        if is_today:
            return BusinessHoursCheckResult(
                is_open=False,
                reason="outside_special_hours",
                period_info={"date": special_date_str},
            )

    # No special hours for this date
    return None


def _check_regular_hours(
    day_of_week: int,
    check_time: time,
    periods: list[dict],
) -> BusinessHoursCheckResult:
    """
    Check if time falls within regular business hours periods.

    Handles overnight hours (e.g., 10PM-2AM) by checking both:
    - Opening portion on the open day
    - Closing portion on the next day (after midnight)

    Args:
        day_of_week: Google format day (0=Sunday, 6=Saturday)
        check_time: Time to check
        periods: List of periods from regular_hours

    Returns:
        BusinessHoursCheckResult
    """
    for period in periods:
        open_info = period.get("open", {})
        close_info = period.get("close", {})

        open_day = open_info.get("day")
        close_day = close_info.get("day")
        open_time = parse_google_time(open_info.get("time", "0000"))
        close_time = parse_google_time(close_info.get("time", "2359"))

        # Case 1: Same day period (most common)
        if open_day == close_day == day_of_week:
            if open_time <= check_time <= close_time:
                return BusinessHoursCheckResult(
                    is_open=True,
                    reason="within_regular_hours",
                    period_info={
                        "day": day_of_week,
                        "open": open_time.strftime("%H:%M"),
                        "close": close_time.strftime("%H:%M"),
                    },
                )

        # Case 2: Overnight period - we're on the opening day
        elif open_day == day_of_week and close_day != day_of_week:
            # Check if we're in the opening portion (after open time)
            if check_time >= open_time:
                return BusinessHoursCheckResult(
                    is_open=True,
                    reason="within_overnight_hours",
                    period_info={
                        "open_day": open_day,
                        "close_day": close_day,
                        "open": open_time.strftime("%H:%M"),
                        "close": close_time.strftime("%H:%M"),
                    },
                )

        # Case 3: Overnight period - we're on the closing day (after midnight)
        elif close_day == day_of_week and open_day == (day_of_week - 1) % 7:
            # Check if we're in the closing portion (before close time)
            if check_time <= close_time:
                return BusinessHoursCheckResult(
                    is_open=True,
                    reason="within_overnight_hours",
                    period_info={
                        "open_day": open_day,
                        "close_day": close_day,
                        "open": open_time.strftime("%H:%M"),
                        "close": close_time.strftime("%H:%M"),
                    },
                )

    # Not within any period
    return BusinessHoursCheckResult(
        is_open=False,
        reason="outside_regular_hours",
        period_info={"day": day_of_week, "time": check_time.strftime("%H:%M")},
    )


def is_within_business_hours(
    captured_at: datetime,
    business_hours: dict | None,
    timezone_str: str | None,
) -> BusinessHoursCheckResult:
    """
    Check if a captured_at timestamp falls within business hours.

    Args:
        captured_at: UTC datetime when the image was captured
        business_hours: JSONB from project.business_hours
        timezone_str: IANA timezone string from project.timezone

    Returns:
        BusinessHoursCheckResult with is_open status and reason

    Edge cases handled:
        - No business_hours data: Returns is_open=True (process by default)
        - Invalid timezone: Falls back to America/Los_Angeles
        - Overnight hours (close time < open time): Handled correctly
        - Special hours: Checked before regular hours
    """
    # No data = process by default
    if not business_hours:
        return BusinessHoursCheckResult(
            is_open=True,
            reason="no_business_hours_data",
            period_info=None,
        )

    # Parse timezone with fallback
    try:
        tz = ZoneInfo(timezone_str or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning(
            f"Invalid timezone '{timezone_str}', using {DEFAULT_TIMEZONE}",
            extra={"invalid_timezone": timezone_str},
        )
        tz = ZoneInfo(DEFAULT_TIMEZONE)

    # Ensure captured_at is timezone-aware
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)

    # Convert to local time
    local_dt = captured_at.astimezone(tz)
    local_date = local_dt.date()
    local_time = local_dt.time()

    # Check special hours first (holidays, closures)
    special_hours = business_hours.get("special_hours", [])
    if special_hours:
        special_result = _check_special_hours(local_date, local_time, special_hours)
        if special_result is not None:
            return special_result

    # Check regular hours
    regular_hours = business_hours.get("regular_hours", {})
    periods = regular_hours.get("periods", [])

    if not periods:
        return BusinessHoursCheckResult(
            is_open=True,
            reason="no_periods_defined",
            period_info=None,
        )

    # Convert Python weekday (0=Monday, 6=Sunday) to Google format (0=Sunday, 6=Saturday)
    python_weekday = local_dt.weekday()
    google_weekday = (python_weekday + 1) % 7

    return _check_regular_hours(google_weekday, local_time, periods)
