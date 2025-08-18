import datetime
from typing import Any, List, Optional, Tuple

from tools.opentable_tool.classes import (
    AvailabilityMetadataResponse,
    AvailabilitySearchResponse,
    CancellationPolicyDetails,
)


def format_availability_results(availability: AvailabilitySearchResponse) -> str:
    """
    Formats the availability search results into a user-friendly string.

    Args:
        availability: The availability search response from the API

    Returns:
        A formatted string with the available times and details
    """
    if (
        not availability
        or not hasattr(availability, "times_available")
        or not availability.times_available
    ):
        return "No availability found."

    restaurant_id = getattr(availability, "rid", "Unknown")
    party_size = getattr(availability, "party_size", "Unknown")

    result = [
        f"Availability for restaurant ID {restaurant_id} (Party of {party_size}):"
    ]

    # Format available times
    if hasattr(availability, "times_available") and availability.times_available:
        for time_slot in availability.times_available:
            # Handle both string and object formats
            if isinstance(time_slot, str):
                # If time_slot is a string (ISO datetime), use it directly
                time_str = time_slot
            else:
                # If time_slot is an object, try to get the time attribute
                time_str = getattr(time_slot, "time", "")

            if time_str:
                # Convert ISO time to more readable format
                try:
                    dt = datetime.datetime.fromisoformat(time_str)
                    formatted_time = dt.strftime("%A, %B %d, %Y at %I:%M %p")
                except ValueError:
                    formatted_time = time_str

                # Add formatted time slot to results
                result.append(f"• {formatted_time}")
    else:
        # Simpler format if times_available is not present
        for time_str in getattr(availability, "times", []):
            try:
                dt = datetime.datetime.fromisoformat(time_str)
                formatted_time = dt.strftime("%I:%M %p")
            except ValueError:
                formatted_time = time_str
            result.append(f"• {formatted_time}")

    # Add no availability reasons if present
    if (
        hasattr(availability, "no_availability_reasons")
        and availability.no_availability_reasons
    ):
        result.append("\nReasons for limited availability:")
        for reason in availability.no_availability_reasons:
            result.append(f"• {reason}")

    return "\n".join(result)


def parse_iso_datetime(
    date_time_str: str,
) -> Tuple[bool, str, Optional[datetime.datetime]]:
    """
    Parses an ISO 8601 datetime string and validates it.

    Args:
        date_time_str: The datetime string to parse

    Returns:
        A tuple of (success, message, datetime_obj)
    """
    if not date_time_str:
        return False, "Datetime string is empty", None

    try:
        # Parse the ISO datetime string
        dt = datetime.datetime.fromisoformat(date_time_str)

        # Validate that minutes are at 15-minute intervals (0, 15, 30, 45)
        if dt.minute % 15 != 0:
            return (
                False,
                f"Minutes must be at 15-minute intervals (0, 15, 30, 45), got: {dt.minute}",
                None,
            )

        # Check that the datetime is not in the past
        now = datetime.datetime.now()
        if dt < now:
            return False, f"Datetime is in the past: {date_time_str}", None

        return True, "", dt
    except ValueError as e:
        return False, f"Invalid ISO datetime format: {str(e)}", None


def format_iso_datetime(dt: datetime.datetime) -> str:
    """
    Format a datetime object to ISO 8601 format required by OpenTable API.
    Adjusts minutes to the nearest 15-minute interval if needed.

    Args:
        dt: The datetime object to format

    Returns:
        String in ISO 8601 format with minutes aligned to 15-minute intervals
    """
    # Adjust minutes to the nearest 15-minute interval (0, 15, 30, 45)
    minute = dt.minute
    remainder = minute % 15

    if remainder > 0:
        # Round up to the next 15-minute interval
        adjusted_minute = minute + (15 - remainder)

        # Create a new datetime with adjusted minutes
        if adjusted_minute >= 60:
            # Handle hour rollover
            new_hour = dt.hour + (adjusted_minute // 60)
            new_minute = adjusted_minute % 60

            # Handle day rollover if needed
            if new_hour >= 24:
                # Handle day, month, and potentially year rollover
                delta_days = new_hour // 24
                new_hour = new_hour % 24
                # Use timedelta to correctly handle month/year boundaries
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                dt = dt + datetime.timedelta(
                    days=delta_days, hours=new_hour, minutes=new_minute
                )
            else:
                dt = dt.replace(hour=new_hour, minute=new_minute)
        else:
            dt = dt.replace(minute=adjusted_minute)

    # Format to ISO 8601 with 'T' separator and without seconds/microseconds
    return dt.strftime("%Y-%m-%dT%H:%M")


def get_valid_search_time(
    time_str: Optional[str] = None, minutes_from_now: int = 0
) -> str:
    """
    Get a valid search time for OpenTable API.
    If time_str is provided, validates and adjusts it to 15-minute intervals.
    If not provided, uses current time + minutes_from_now, adjusted to 15-minute intervals.

    Args:
        time_str: Optional ISO format time string
        minutes_from_now: Minutes to add to current time if time_str not provided

    Returns:
        Valid ISO format time string aligned to 15-minute intervals
    """
    # Initialize a datetime object to use for formatting
    dt = datetime.datetime.now() + datetime.timedelta(minutes=minutes_from_now)

    if time_str:
        # Parse and validate the provided time string
        success, _, parsed_dt = parse_iso_datetime(time_str)
        # Only use the parsed dt if it was valid
        if success and parsed_dt is not None:
            dt = parsed_dt

    # Format with 15-minute interval alignment
    return format_iso_datetime(dt)


def validate_search_parameters(
    party_size: int,
    start_time: Optional[str] = None,
    forward_minutes: int = 120,
    backward_minutes: int = 120,
) -> Tuple[bool, str, dict]:
    """
    Validate search parameters for OpenTable availability search.

    Args:
        party_size: Number of diners
        start_time: Start time in ISO format (optional)
        forward_minutes: Minutes to search forward
        backward_minutes: Minutes to search backward

    Returns:
        Tuple of (is_valid, error_message, validated_params)
    """
    validated_params = {}

    # Validate party_size
    if not isinstance(party_size, int) or party_size <= 0:
        return False, f"Party size must be a positive integer, got: {party_size}", {}
    validated_params["party_size"] = party_size

    # Validate time parameters
    if start_time:
        success, message, dt = parse_iso_datetime(start_time)
        if not success:
            return False, f"Invalid start_time: {message}", {}
        validated_params["start_date_time"] = start_time
    else:
        # Use current time if not provided
        validated_params["start_date_time"] = get_valid_search_time()

    # Validate forward_minutes
    if (
        not isinstance(forward_minutes, int)
        or forward_minutes < 0
        or forward_minutes > 720
    ):
        return (
            False,
            f"forward_minutes must be between 0 and 720, got: {forward_minutes}",
            {},
        )
    validated_params["forward_minutes"] = forward_minutes

    # Validate backward_minutes
    if (
        not isinstance(backward_minutes, int)
        or backward_minutes < 0
        or backward_minutes > 720
    ):
        return (
            False,
            f"backward_minutes must be between 0 and 720, got: {backward_minutes}",
            {},
        )
    validated_params["backward_minutes"] = backward_minutes

    return True, "", validated_params


def format_table_attributes(attributes: List[str]) -> str:
    """
    Format a list of table attributes into the format required by the API.

    Args:
        attributes: List of table attributes (e.g., ["default", "outdoor", "bar"])

    Returns:
        Formatted string of attributes for the require_attributes parameter
    """
    valid_attributes = ["default", "hightop", "bar", "counter", "outdoor"]
    # Filter to only include valid attributes
    valid_selected = [attr for attr in attributes if attr.lower() in valid_attributes]

    if not valid_selected:
        # Default to 'default' if no valid attributes
        return "default"

    return ",".join(valid_selected)


def extract_booking_url(time_slot: Any, is_affiliate: bool = True) -> Optional[str]:
    """
    Extract the appropriate booking URL from a time slot based on the user type.

    Args:
        time_slot: The time slot object from the API response
        is_affiliate: Whether the requestor is an affiliate partner (True) or restaurant (False)

    Returns:
        The appropriate booking URL or None if not found
    """
    if not time_slot:
        return None

    booking_url = None

    # Navigate through the nested structure using getattr for class objects
    availability_types = getattr(time_slot, "availability_types", [])
    if availability_types:
        for avail_type in availability_types:
            dining_areas = getattr(avail_type, "dining_area", [])
            if dining_areas:
                for area in dining_areas:
                    # Use booking_url for affiliates, booking_restref_url for restaurants
                    if is_affiliate:
                        booking_url = getattr(area, "booking_url", None)
                        if booking_url:
                            break
                    else:
                        booking_url = getattr(area, "booking_restref_url", None)
                        if booking_url:
                            break

                if booking_url:
                    break

    return booking_url


def parse_no_availability_reasons(reasons: List[str]) -> str:
    """
    Parse and explain the no_availability_reasons from the API response.

    Args:
        reasons: List of reason codes from the API

    Returns:
        User-friendly explanation of why availability might be limited
    """
    if not reasons:
        return ""

    # Map of reason codes to user-friendly explanations
    reason_explanations = {
        "NoTimesExist": "No available times exist for this request.",
        "BelowMinPartySize": "The requested party size is below the minimum allowed.",
        "AboveMaxPartySize": "The requested party size is above the maximum allowed.",
        "OutsideOperatingHours": "The requested time is outside the restaurant's operating hours.",
        "RestaurantOfflineMode": "The restaurant is currently operating in offline mode.",
        "NoAvailabilityOnDate": "No availability for the selected date.",
        "RestaurantTemporarilyClosed": "The restaurant is temporarily closed.",
        "AvailabilityNotYetReleased": "Availability for this date has not been released yet.",
    }

    result = []
    for reason in reasons:
        explanation = reason_explanations.get(reason, reason)
        result.append(explanation)

    return "\n".join(result)


def format_availability_metadata(metadata: AvailabilityMetadataResponse) -> str:
    """
    Formats the availability metadata into a user-friendly string.

    Args:
        metadata: The availability metadata response from the API

    Returns:
        A formatted string with the dining areas and attributes
    """
    if not metadata or not hasattr(metadata, "data"):
        return "No metadata available."

    result = ["Restaurant Environment and Dining Areas:"]

    # Format environments
    if hasattr(metadata.data, "environments") and metadata.data.environments:
        result.append("\nAvailable Environments:")
        for env in metadata.data.environments:
            result.append(f"• {env}")

    # Format attributes
    if hasattr(metadata.data, "attributes") and metadata.data.attributes:
        result.append("\nAvailable Table Attributes:")
        for attr in metadata.data.attributes:
            result.append(f"• {attr}")

    # Format dining areas
    if hasattr(metadata.data, "dining_areas") and metadata.data.dining_areas:
        result.append("\nDining Areas:")
        for area in metadata.data.dining_areas:
            area_name = getattr(area, "name", "Unnamed Area")
            area_desc = getattr(area, "description", "No description")
            area_env = getattr(area, "environment", "Unknown environment")
            area_id = getattr(area, "id", "Unknown ID")

            area_info = f"• {area_name} (ID: {area_id})"
            if area_env:
                area_info += f" - {area_env}"
            if area_desc and area_desc != area_name:
                area_info += f"\n  Description: {area_desc}"

            result.append(area_info)

    return "\n".join(result)


def format_cancellation_policy(policy: CancellationPolicyDetails) -> str:
    """
    Formats the cancellation policy details into a user-friendly string.

    Args:
        policy: The cancellation policy details from the API

    Returns:
        A formatted string with the cancellation policy information
    """
    if not policy:
        return "No cancellation policy information available."

    # Format the basic policy information
    result = [f"Cancellation Policy for Party of {policy.party_size}:"]
    result.append(f"Policy Type: {policy.policy_type}")

    # Format deposit details
    if hasattr(policy, "deposit_details"):
        deposit = policy.deposit_details

        # Calculate the actual amount in major currency units
        amount_major = deposit.amount / deposit.denominator

        # Determine if the deposit is per guest or total
        if deposit.type == "PerGuest":
            deposit_type = f"{amount_major} {deposit.currency} per guest"
            total = amount_major * policy.party_size
            deposit_type += f" (Total: {total} {deposit.currency})"
        else:
            deposit_type = f"{amount_major} {deposit.currency} total"

        result.append(f"Deposit Required: {deposit_type}")

    # Format cutoff information
    if hasattr(policy, "cut_off"):
        cutoff = policy.cut_off

        if cutoff.cutoff_type == "DaysBefore":
            cutoff_info = f"{cutoff.days_before_cutoff} days before the reservation"
        else:
            cutoff_info = cutoff.cutoff_type

        result.append(f"Cancellation Cutoff: {cutoff_info}")

        # Add explanation of what the cutoff means
        if cutoff.cutoff_type == "DaysBefore":
            explanation = (
                f"You must cancel at least {cutoff.days_before_cutoff} days before "
                f"your reservation to avoid possible charges."
            )
            result.append(f"Note: {explanation}")

    return "\n".join(result)


def format_cancellation_policy_for_timeslot(cancellation_policy: Any) -> str:
    """
    Formats the cancellation policy information from a timeslot's availability_types
    into a user-friendly string.

    Args:
        cancellation_policy: The cancellation policy object from a timeslot's availability_types

    Returns:
        A formatted string with basic cancellation policy information
    """
    if not cancellation_policy:
        return "No cancellation policy information."

    policy_type = getattr(cancellation_policy, "type", "Unknown")
    policy_id = getattr(cancellation_policy, "id", "Unknown")

    result = [f"Cancellation Policy: {policy_type} (ID: {policy_id})"]

    # Add deposit information if available
    amount = getattr(cancellation_policy, "amount", None)
    currency = getattr(cancellation_policy, "currency", None)
    denominator = getattr(cancellation_policy, "denominator", None)
    deposit_type = getattr(cancellation_policy, "deposit_type", None)

    if amount is not None and currency and denominator is not None and denominator != 0:
        amount_major = amount / denominator
        deposit_info = f"{amount_major} {currency}"

        if deposit_type == "PerGuest":
            deposit_info += " per guest"

        result.append(f"Deposit: {deposit_info}")

    return "\n".join(result)


def validate_cancellation_policy_parameters(
    restaurant_id: int,
    cancellation_id: str,
) -> Tuple[bool, str, dict]:
    """
    Validate parameters for OpenTable cancellation policy API.

    Args:
        restaurant_id: The restaurant ID (rid)
        cancellation_id: The cancellation policy ID

    Returns:
        Tuple of (is_valid, error_message, validated_params)
    """
    validated_params = {}

    # Validate restaurant_id
    if not isinstance(restaurant_id, int) or restaurant_id <= 0:
        return (
            False,
            f"Restaurant ID must be a positive integer, got: {restaurant_id}",
            {},
        )
    validated_params["restaurant_id"] = restaurant_id

    # Validate cancellation_id
    if not cancellation_id or not isinstance(cancellation_id, str):
        return (
            False,
            f"Cancellation ID must be a non-empty string, got: {cancellation_id}",
            {},
        )
    validated_params["cancellation_id"] = cancellation_id

    return True, "", validated_params


def calculate_cancellation_fee(
    policy: CancellationPolicyDetails,
    reservation_datetime: datetime.datetime,
    current_datetime: Optional[datetime.datetime] = None,
) -> Tuple[bool, float, str]:
    """
    Calculate potential cancellation fee based on cancellation policy and dates.

    Args:
        policy: The cancellation policy details
        reservation_datetime: The datetime of the reservation
        current_datetime: The current datetime (defaults to now if not provided)

    Returns:
        Tuple of (fee_applies, fee_amount, explanation)
    """
    if current_datetime is None:
        current_datetime = datetime.datetime.now()

    if (
        not policy
        or not hasattr(policy, "cut_off")
        or not hasattr(policy, "deposit_details")
    ):
        return False, 0.0, "No valid cancellation policy available."

    # Get policy details
    cutoff = policy.cut_off
    deposit = policy.deposit_details

    # Calculate fee amount (default to 0)
    fee_amount = 0.0
    fee_applies = False

    if policy.policy_type != "Deposit":
        return False, 0.0, f"No cancellation fee for policy type: {policy.policy_type}"

    # Calculate precise days (can be fractional)
    delta_seconds = (reservation_datetime - current_datetime).total_seconds()
    days_until_reservation = delta_seconds / 86_400

    # Past reservations – no fee logic needed
    if days_until_reservation < 0:
        return False, 0.0, "Reservation date is in the past."

    # Check if we're within the cutoff period
    if cutoff.cutoff_type == "DaysBefore":
        fee_applies = days_until_reservation < float(cutoff.days_before_cutoff)

        if fee_applies:
            # Calculate the fee based on deposit details
            if deposit.denominator == 0:
                amount_major = 0.0  # Default to zero if denominator is zero
            else:
                amount_major = deposit.amount / deposit.denominator

            if deposit.type == "PerGuest":
                fee_amount = float(amount_major * policy.party_size)
                explanation = (
                    f"Cancellation fee applies: {days_until_reservation:.2f} days until reservation, "
                    f"which is less than the required {cutoff.days_before_cutoff} days notice. "
                    f"Fee: {amount_major} {deposit.currency} per guest × {policy.party_size} guests = "
                    f"{fee_amount} {deposit.currency}"
                )
            else:
                fee_amount = float(amount_major)
                explanation = (
                    f"Cancellation fee applies: {days_until_reservation:.2f} days until reservation, "
                    f"which is less than the required {cutoff.days_before_cutoff} days notice. "
                    f"Fee: {fee_amount} {deposit.currency}"
                )
        else:
            explanation = (
                f"No cancellation fee: {days_until_reservation:.2f} days until reservation, "
                f"which is at least the required {cutoff.days_before_cutoff} days notice."
            )
    else:
        explanation = f"Unable to calculate cancellation fee for cutoff type: {cutoff.cutoff_type}"

    return fee_applies, fee_amount, explanation
