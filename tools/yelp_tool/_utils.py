import re
from datetime import datetime
from typing import List, Optional, Tuple

from tools.yelp_tool.classes import (
    YelpBookingsHoldsRequest,
    YelpBookingsHoldsResponse,
    YelpBookingsOpeningsRequest,
    YelpBookingsOpeningsResponse,
    YelpBookingsReservationsRequest,
    YelpBookingsReservationsResponse,
)


def _validate_business_id_or_alias(business_id_or_alias: str) -> List[str]:
    """
    Validate business ID or alias according to Yelp's requirements.

    Args:
        business_id_or_alias: Business ID or alias to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not business_id_or_alias:
        errors.append("Business ID/alias must be provided")
        return errors

    # Pattern matches either a 22-character alphanumeric Yelp Business ID
    # or a business alias (1-255 chars, alphanumeric + hyphens)
    pattern = r"^(?:[A-Za-z0-9]{22}|[A-Za-z0-9-]{1,255})$"

    if not re.match(pattern, business_id_or_alias):
        if len(business_id_or_alias) == 22:
            errors.append(
                "22-character Business ID can only contain letters and numbers"
            )
        elif len(business_id_or_alias) > 255:
            errors.append("Business alias must be under 255 characters")
        else:
            errors.append(
                "Business alias can only contain letters, numbers, and hyphens"
            )

    return errors


def _validate_covers(covers: int) -> List[str]:
    """
    Validate covers count.

    Args:
        covers: Number of people

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not (1 <= covers <= 10):
        errors.append("Number of people must be between 1 and 10")

    return errors


def _validate_date(date: str) -> List[str]:
    """
    Validate date format.

    Args:
        date: Date string to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        errors.append("Date must be in YYYY-MM-DD format (e.g., 2024-12-25)")

    return errors


def _validate_time(time: str) -> List[str]:
    """
    Validate time format.

    Args:
        time: Time string to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        errors.append("Time must be in HH:MM format (e.g., 18:30)")

    return errors


def _validate_unique_id(unique_id: str) -> List[str]:
    """
    Validate unique ID.

    Args:
        unique_id: Unique ID to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not unique_id or len(unique_id) > 300:
        errors.append("Unique ID must be provided and under 300 characters")

    return errors


def _validate_email(email: str) -> List[str]:
    """
    Validate email format.

    Args:
        email: Email address to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not email:
        errors.append("Email must be provided")
        return errors

    # Basic email validation pattern
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(email_pattern, email):
        errors.append("Invalid email format")

    return errors


def _validate_phone(phone: str) -> List[str]:
    """
    Validate phone number format.

    Args:
        phone: Phone number to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not phone:
        errors.append("Phone number must be provided")
        return errors

    if len(phone) > 32:
        errors.append("Phone number must be under 32 characters")

    return errors


def _validate_name(name: str, field_name: str) -> List[str]:
    """
    Validate name field.

    Args:
        name: Name to validate
        field_name: Name of the field for error messages

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not name or not name.strip():
        errors.append(f"{field_name} must be provided")

    return errors


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

    # Use helper functions for validation
    errors.extend(_validate_business_id_or_alias(business_id_or_alias))
    errors.extend(_validate_covers(covers))
    errors.extend(_validate_date(date))
    errors.extend(_validate_time(time))

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


def format_openings_for_llm(openings_response: YelpBookingsOpeningsResponse) -> str:
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


def create_holds_request(
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    unique_id: str,
) -> Tuple[bool, str, Optional[YelpBookingsHoldsRequest]]:
    """
    Validate parameters and create YelpBookingsHoldsRequest object.
    Provides early validation with user-friendly error messages.

    Args:
        business_id_or_alias: Business ID or alias
        covers: Number of people for the reservation
        date: Date in YYYY-mm-dd format
        time: Time in HH:MM format
        unique_id: Unique user/device identifier

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpBookingsHoldsRequest]: Request object or None
    """
    errors = []

    # Use helper functions for validation
    errors.extend(_validate_business_id_or_alias(business_id_or_alias))
    errors.extend(_validate_covers(covers))
    errors.extend(_validate_date(date))
    errors.extend(_validate_time(time))
    errors.extend(_validate_unique_id(unique_id))

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Create request object
    try:
        request_obj = YelpBookingsHoldsRequest(
            business_id_or_alias=business_id_or_alias,
            covers=covers,
            date=date,
            time=time,
            unique_id=unique_id,
        )
        return True, "Hold request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create hold request: {str(e)}", None


def format_holds_response_for_llm(holds_response: YelpBookingsHoldsResponse) -> str:
    """
    Format the holds response into a human-readable string for display.

    Args:
        holds_response: Parsed holds response object

    Returns:
        str: Formatted string representation of the hold information
    """
    # Convert Unix timestamp to readable format
    try:
        expires_dt = datetime.fromtimestamp(holds_response.expires_at)
        expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        expires_str = "Invalid timestamp"

    try:
        last_cancel_dt = datetime.fromtimestamp(holds_response.last_cancellation_date)
        last_cancel_str = last_cancel_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        last_cancel_str = "Invalid timestamp"

    result_lines = [
        "Reservation Hold Created Successfully!",
        f"Hold ID: {holds_response.hold_id}",
        f"Expires at: {expires_str}",
        f"Credit card required: {'Yes' if holds_response.credit_card_hold else 'No'}",
        f"Reservation editable: {'Yes' if holds_response.is_editable else 'No'}",
        f"Last cancellation date: {last_cancel_str}",
    ]

    if holds_response.notes:
        result_lines.append(f"Restaurant notes: {holds_response.notes}")

    if holds_response.cancellation_policy:
        result_lines.append(
            f"Cancellation policy: {holds_response.cancellation_policy}"
        )

    if holds_response.reserve_url:
        result_lines.append(
            f"Alternative reservation URL: {holds_response.reserve_url}"
        )

    return "\n".join(result_lines)


def create_reservation_request_from_hold(
    holds_response: YelpBookingsHoldsResponse,
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    first_name: str,
    last_name: str,
    phone: str,
    email: str,
    unique_id: str,
    notes: Optional[str] = None,
) -> Tuple[bool, str, Optional[YelpBookingsReservationsRequest]]:
    """
    Create a reservation request using the hold_id from a previous hold response.
    This helper function connects the hold response to the reservation API request.

    Args:
        holds_response: Previous hold response containing the hold_id
        business_id_or_alias: Business ID or alias (must match the hold request)
        covers: Number of people (must match the hold request)
        date: Date in YYYY-mm-dd format (must match the hold request)
        time: Time in HH:MM format (must match the hold request)
        first_name: First name of the person making the reservation
        last_name: Last name of the person making the reservation
        phone: Phone number for the reservation
        email: Email address for the reservation
        unique_id: Unique user/device identifier (must match the hold request)
        notes: Optional special notes for the reservation

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpBookingsReservationsRequest]: Request object or None
    """
    errors = []

    # Validate all required fields
    errors.extend(_validate_business_id_or_alias(business_id_or_alias))
    errors.extend(_validate_covers(covers))
    errors.extend(_validate_date(date))
    errors.extend(_validate_time(time))
    errors.extend(_validate_name(first_name, "First name"))
    errors.extend(_validate_name(last_name, "Last name"))
    errors.extend(_validate_phone(phone))
    errors.extend(_validate_email(email))
    errors.extend(_validate_unique_id(unique_id))

    # Validate that hold_id exists
    if not holds_response.hold_id:
        errors.append("Hold ID is required from the hold response")

    # Check if hold has expired (optional warning, not blocking)
    current_time = datetime.now().timestamp()
    if current_time > holds_response.expires_at:
        errors.append("Warning: Hold has expired. You may need to create a new hold.")

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Create reservation request object
    try:
        request_obj = YelpBookingsReservationsRequest(
            business_id_or_alias=business_id_or_alias,
            covers=covers,
            date=date,
            time=time,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            hold_id=holds_response.hold_id,
            unique_id=unique_id,
            notes=notes,
        )
        return True, "Reservation request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create reservation request: {str(e)}", None


def format_reservation_response_for_llm(
    reservation_response: YelpBookingsReservationsResponse,
) -> str:
    """
    Format the reservation response into a human-readable string for display.

    Args:
        reservation_response: YelpBookingsReservationsResponse object

    Returns:
        str: Formatted string representation of the reservation confirmation
    """
    result_lines = [
        "🎉 Reservation Confirmed Successfully!",
        f"Reservation ID: {reservation_response.reservation_id}",
        f"Confirmation URL: {reservation_response.confirmation_url}",
    ]

    if reservation_response.notes:
        result_lines.append(f"Restaurant notes: {reservation_response.notes}")

    result_lines.append(
        "\nPlease save your reservation ID and visit the confirmation URL for details."
    )

    return "\n".join(result_lines)


def create_reservation_from_hold_response(
    holds_response: YelpBookingsHoldsResponse,
    holds_request: YelpBookingsHoldsRequest,
    first_name: str,
    last_name: str,
    phone: str,
    email: str,
    notes: Optional[str] = None,
) -> Tuple[bool, str, Optional[YelpBookingsReservationsRequest]]:
    """
    Simplified helper to create reservation request from hold response and original hold request.
    This function reuses the parameters from the original hold request to ensure consistency.

    Args:
        holds_response: The response from the hold API containing hold_id
        holds_request: The original hold request to reuse parameters from
        first_name: First name of the person making the reservation
        last_name: Last name of the person making the reservation
        phone: Phone number for the reservation
        email: Email address for the reservation
        notes: Optional special notes for the reservation

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpBookingsReservationsRequest]: Request object or None
    """
    return create_reservation_request_from_hold(
        holds_response=holds_response,
        business_id_or_alias=holds_request.business_id_or_alias,
        covers=holds_request.covers,
        date=holds_request.date,
        time=holds_request.time,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        unique_id=holds_request.unique_id,
        notes=notes,
    )
