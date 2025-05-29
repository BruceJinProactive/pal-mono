import re
from datetime import datetime
from typing import Optional, Tuple

from tools.yelp_tool.classes import (
    YelpBookingsOpeningsRequest,
    YelpBookingsOpeningsResponse,
)


def create_openings_request(
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    get_covers_range: Optional[bool] = None,
) -> Tuple[bool, str, Optional[YelpBookingsOpeningsRequest]]:
    """
    Validate parameters and create YelpBookingsOpeningsRequest object.
    Provides early validation with user-friendly error messages.

    Args:
        business_id_or_alias: Business ID or alias
        covers: Number of people for the reservation
        date: Date in YYYY-mm-dd format
        time: Time in HH:MM format
        get_covers_range: Whether to include covers range in response

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpBookingsOpeningsRequest]: Request object or None
    """
    errors = []

    # Validate business ID/alias - simplified check
    if not business_id_or_alias or len(business_id_or_alias) > 255:
        errors.append("Business ID/alias must be provided and under 255 characters")
    elif not re.match(r"^[A-Za-z0-9-]+$", business_id_or_alias):
        errors.append(
            "Business ID/alias can only contain letters, numbers, and hyphens"
        )

    # Validate covers count
    if not (1 <= covers <= 10):
        errors.append("Number of people must be between 1 and 10")

    # Validate date format using datetime parsing
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        errors.append("Date must be in YYYY-MM-DD format (e.g., 2024-12-25)")

    # Validate time format using datetime parsing
    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        errors.append("Time must be in HH:MM format (e.g., 18:30)")

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Create request object
    try:
        request_obj = YelpBookingsOpeningsRequest(
            business_id_or_alias=business_id_or_alias,
            covers=covers,
            date=date,
            time=time,
            get_covers_range=get_covers_range,
        )
        return True, "Request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create request: {str(e)}", None


def format_openings_for_display(openings_response: YelpBookingsOpeningsResponse) -> str:
    """
    Format the openings response into a human-readable string for display.

    Args:
        openings_response: Parsed openings response object

    Returns:
        str: Formatted string representation of available reservation times
    """
    if not openings_response.reservation_times:
        return "No available reservation times found."

    result_lines = ["Available Reservation Times:"]

    for daily_times in openings_response.reservation_times:
        if not daily_times.times:
            continue

        # Format date for display
        try:
            date_obj = datetime.strptime(daily_times.date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
        except ValueError:
            formatted_date = daily_times.date

        result_lines.append(f"\n{formatted_date}:")

        # Group times by credit card requirement
        no_cc_times = [t.time for t in daily_times.times if not t.credit_card_required]
        cc_required_times = [
            t.time for t in daily_times.times if t.credit_card_required
        ]

        if no_cc_times:
            result_lines.append(
                f"  Available times (no credit card required): {', '.join(no_cc_times)}"
            )

        if cc_required_times:
            result_lines.append(
                f"  Available times (credit card required): {', '.join(cc_required_times)}"
            )

    # Add covers range information if available
    if openings_response.covers_range:
        result_lines.append(
            f"\nParty size range: {openings_response.covers_range.min_party_size}-{openings_response.covers_range.max_party_size} people"
        )

    return "\n".join(result_lines)
