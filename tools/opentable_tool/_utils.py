import datetime
from typing import Optional, Tuple

from tools.opentable_tool.classes import AvailabilitySearchResponse


def format_availability_results(availability: AvailabilitySearchResponse) -> str:
    """
    Format a list of available times into a user-friendly string.

    Assumes a well-formed AvailabilitySearchResponse from our API layer.
    """
    if not availability.times_available:
        return "No availability found."

    header = (
        f"Availability for restaurant ID {availability.rid} "
        f"(Party of {availability.party_size}):"
    )

    lines = [header]
    for time_str in availability.times_available:
        try:
            dt = datetime.datetime.fromisoformat(time_str)
            pretty = dt.strftime("%A, %B %d, %Y at %I:%M %p")
        except ValueError:
            pretty = time_str
        lines.append(f"• {pretty}")

    return "\n".join(lines)


def parse_iso_datetime(
    date_time_str: str,
) -> Tuple[bool, str, Optional[datetime.datetime]]:
    """
    Parse an ISO 8601 datetime string.

    Returns (success, message, datetime_obj). No minute-interval enforcement.
    """
    if not date_time_str:
        return False, "Datetime string is empty", None

    try:
        dt = datetime.datetime.fromisoformat(date_time_str)
        return True, "", dt
    except ValueError as e:
        return False, f"Invalid ISO datetime format: {str(e)}", None


def format_iso_datetime(dt: datetime.datetime) -> str:
    """
    Format to ISO 8601 (YYYY-MM-DDTHH:MM), rounding minutes up to the next
    15-minute boundary (or leaving as-is if already aligned).
    """
    dt = dt.replace(second=0, microsecond=0)
    add_minutes = (15 - (dt.minute % 15)) % 15
    if add_minutes:
        dt = dt + datetime.timedelta(minutes=add_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M")


def validate_search_parameters(
    party_size: int,
    start_time: Optional[str] = None,
) -> Tuple[bool, str, dict]:
    """
    Validate inputs and return normalized parameters for availability search.
    """
    params: dict = {}

    if party_size <= 0:
        return False, f"Party size must be a positive integer, got: {party_size}", {}
    params["party_size"] = party_size

    if start_time:
        ok, msg, dt = parse_iso_datetime(start_time)
        if not ok or dt is None:
            return False, f"Invalid start_time: {msg}", {}
        params["start_date_time"] = format_iso_datetime(dt)
    else:
        now = datetime.datetime.now()
        params["start_date_time"] = format_iso_datetime(now)

    return True, "", params
