import datetime
from typing import Optional, Tuple

from tools.opentable_tool.classes import AvailabilitySearchResponse


def format_availability_results(availability: AvailabilitySearchResponse) -> str:
    """Render availability slots in a compact, human-friendly format."""

    if not availability.times_available:
        return "No availability found."

    header = (
        f"Availability for restaurant ID {availability.rid} "
        f"(Party of {availability.party_size}):"
    )

    pretty_slots = []
    for slot in availability.times_available:
        try:
            dt = datetime.datetime.fromisoformat(slot)
            pretty_slots.append(dt.strftime("%A, %B %d, %Y at %I:%M %p"))
        except ValueError:
            pretty_slots.append(slot)

    lines = [header, *(f"• {value}" for value in pretty_slots)]
    return "\n".join(lines)


def _round_to_quarter_hour(dt: datetime.datetime) -> datetime.datetime:
    dt = dt.replace(second=0, microsecond=0)
    offset = (15 - (dt.minute % 15)) % 15
    return dt + datetime.timedelta(minutes=offset)


def validate_search_parameters(
    party_size: int,
    start_time: Optional[str] = None,
) -> Tuple[bool, str, dict]:
    """Ensure incoming reservation parameters match the API contract."""

    if party_size <= 0:
        return False, f"Party size must be a positive integer, got: {party_size}", {}

    try:
        base_time = (
            datetime.datetime.fromisoformat(start_time)
            if start_time
            else datetime.datetime.now()
        )
    except ValueError as exc:
        return False, f"Invalid start_time: {exc}", {}

    normalized_time = _round_to_quarter_hour(base_time).strftime("%Y-%m-%dT%H:%M")
    return True, "", {"party_size": party_size, "start_date_time": normalized_time}
