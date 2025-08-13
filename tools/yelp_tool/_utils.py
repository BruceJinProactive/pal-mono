import re
from datetime import datetime
from typing import Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

from tools.yelp_tool._apis import create_reservation_creditcard_not_required
from tools.yelp_tool.classes import (
    YelpAccessToken,
    YelpBookingsHoldsRequestCreditCardNotRequired,
    YelpBookingsHoldsResponseCreditCardNotRequired,
    YelpBookingsOpeningsRequestCreditCardNotRequired,
    YelpBookingsOpeningsRequestCreditCardRequired,
    YelpBookingsOpeningsResponseCreditCardNotRequired,
    YelpBookingsOpeningsResponseCreditCardRequired,
    YelpBookingsReservationsRequestCreditCardNotRequired,
    YelpCancelVisitRequest,
    YelpCancelVisitResponse,
    YelpWaitlistInfoRequest,
    YelpWaitlistInfoResponse,
    YelpWaitlistJoinQueueRequest,
    YelpWaitlistJoinQueueResponse,
    YelpWaitlistOnMyWayRequest,
    YelpWaitlistOnMyWayResponse,
    YelpWaitlistStatusRequest,
    YelpWaitlistStatusResponse,
)
from utils.log import logger

# Number of results to request when the caller explicitly asks for the full list
OPENINGS_FULL_LIST_COUNT = 10


def normalize_openings_counts(
    num_results_before: Optional[int],
    num_results_after: Optional[int],
) -> Tuple[Optional[int], Optional[int]]:
    """
    Normalize openings pagination counts. If both values are explicitly 0,
    coerce both to OPENINGS_FULL_LIST_COUNT.

    Returns the possibly modified (num_results_before, num_results_after).
    """
    if num_results_after == 0 and num_results_before == 0:
        logger.info(
            f"[YelpTool.openings] Both num_results_after and num_results_before are 0; setting both to {OPENINGS_FULL_LIST_COUNT} to request full availability list."
        )
        return OPENINGS_FULL_LIST_COUNT, OPENINGS_FULL_LIST_COUNT
    return num_results_before, num_results_after


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


def _validate_phone_e164(phone: str) -> List[str]:
    """
    Validate phone number for E.164 format requirements.

    Args:
        phone: Phone number to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not phone:
        errors.append("Phone number must be provided")
        return errors

    # Remove spaces, dashes, parentheses for basic validation
    cleaned_phone = re.sub(r"[\s\-\(\)]", "", phone)

    # Check if it's already in E.164 format
    e164_pattern = r"^\+[1-9]\d{1,14}$"
    if re.match(e164_pattern, phone):
        return errors  # Already valid E.164

    # Check if it's a US number that can be converted to E.164
    us_pattern = r"^(\+?1)?[2-9]\d{2}[2-9]\d{2}\d{4}$"
    if re.match(us_pattern, cleaned_phone):
        return errors  # Can be converted to E.164

    # Check for basic phone number structure
    if len(cleaned_phone) < 7 or len(cleaned_phone) > 15:
        errors.append("Phone number must be between 7 and 15 digits")
    elif not cleaned_phone.isdigit() and not phone.startswith("+"):
        errors.append(
            "Phone number can only contain digits, spaces, dashes, parentheses, and + symbol"
        )

    return errors


def _validate_party_size(party_size: int) -> List[str]:
    """
    Validate party size for waitlist.

    Args:
        party_size: Number of people in the party

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if party_size < 1:
        errors.append("Party size must be at least 1 person")

    # Most restaurants have practical limits, but API doesn't specify a max
    if party_size > 20:
        errors.append("Party size seems unusually large (over 20 people)")

    return errors


def _validate_arrival_time(arrival_time: int, field_name: str) -> List[str]:
    """
    Validate arrival time range for waitlist on-my-way.

    Args:
        arrival_time: Arrival time in minutes from now
        field_name: Name of the field for error messages

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if arrival_time < 1:
        errors.append(f"{field_name} must be at least 1 minute")
    elif arrival_time > 30:
        errors.append(f"{field_name} must be 30 minutes or less")

    return errors


def _normalize_phone_to_e164(phone: str) -> str:
    """
    Convert phone number to E.164 format.

    Args:
        phone: Phone number in various formats

    Returns:
        Phone number in E.164 format

    Raises:
        ValueError: If the phone number is invalid
    """
    if not phone or not phone.strip():
        raise ValueError("Phone number cannot be empty")

    # Remove all non-digit characters except +
    cleaned = re.sub(r"[^\d+]", "", phone)

    # Extract digits only
    digits_only = re.sub(r"[^\d]", "", cleaned)

    # Basic length validation
    if len(digits_only) < 7 or len(digits_only) > 15:
        raise ValueError(f"Invalid phone number length: {len(digits_only)} digits")

    # If already in E.164 format, return as-is
    if cleaned.startswith("+"):
        return cleaned

    # Handle US numbers
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    elif len(digits_only) == 11 and digits_only.startswith("1"):
        return f"+{digits_only}"

    # For other numbers, add + prefix
    return f"+{digits_only}"


def check_waitlist_on_my_way_required_fields(
    business_id: Optional[str] = None,
    phone: Optional[str] = None,
    party_size: Optional[int] = None,
    name: Optional[str] = None,
    arrival_range_max: Optional[int] = None,
    arrival_range_min: Optional[int] = None,
) -> Tuple[bool, List[str]]:
    """
    Check which required fields are missing for waitlist on-my-way creation.
    All fields including arrival times are required by the API.

    Args:
        business_id: Yelp business ID
        phone: Patron's phone number
        party_size: Number of people in the party
        name: Patron's full name
        arrival_range_max: Maximum expected arrival time in minutes (REQUIRED)
        arrival_range_min: Minimum expected arrival time in minutes (REQUIRED)

    Returns:
        Tuple containing:
        - bool: True if all required fields are present, False otherwise
        - List[str]: List of missing required fields with user-friendly prompts
    """
    missing_fields = []

    if not business_id:
        missing_fields.append("business_id")

    if not name or not name.strip():
        missing_fields.append("What name should I put for the waitlist?")

    if not phone:
        missing_fields.append("What phone number should I use for the waitlist?")

    if not party_size or party_size < 1:
        missing_fields.append("How many people are in your party?")

    if arrival_range_min is None or arrival_range_min < 1:
        missing_fields.append(
            "What is the minimum time it might take you to arrive? Please provide a time estimate (e.g., 15 minutes, 10-20 minutes)"
        )

    if arrival_range_max is None or arrival_range_max < 1:
        # Only add this if min is provided but max is missing
        if arrival_range_min is not None and arrival_range_min >= 1:
            missing_fields.append(
                "What's the maximum time it might take you to arrive?"
            )

    # If both arrival times are missing, just ask once
    if (arrival_range_min is None or arrival_range_min < 1) and (
        arrival_range_max is None or arrival_range_max < 1
    ):
        # Remove individual arrival time prompts and add a single one
        missing_fields = [
            field
            for field in missing_fields
            if not field.startswith("How long until")
            and not field.startswith("What's the maximum")
        ]
        missing_fields.append(
            "How long until you arrive? Please provide a time estimate (e.g., 15 minutes, 10-20 minutes)"
        )

    return len(missing_fields) == 0, missing_fields


def create_openings_request_creditcard_not_required(
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    get_covers_range: Optional[bool] = None,
    num_results_after: Optional[int] = None,
    num_results_before: Optional[int] = None,
) -> Tuple[bool, str, Optional[YelpBookingsOpeningsRequestCreditCardNotRequired]]:
    """
    Validate parameters and create YelpBookingsOpeningsRequestCreditCardNotRequired object for credit card not required workflow.
    Provides early validation with user-friendly error messages.

    Args:
        business_id_or_alias: Business ID or alias
        covers: Number of people for the reservation
        date: Date in YYYY-mm-dd format
        time: Time in HH:MM format
        get_covers_range: Whether to include covers range in response
        num_results_after: Set to 0 to include openings before the requested time; if both after and before are 0, both will be coerced to OPENINGS_FULL_LIST_COUNT
        num_results_before: Set to 0 to include openings after the requested time; if both after and before are 0, both will be coerced to OPENINGS_FULL_LIST_COUNT

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpBookingsOpeningsRequestCreditCardNotRequired]: Request object or None
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

    # Normalize counts
    num_results_before, num_results_after = normalize_openings_counts(
        num_results_before, num_results_after
    )

    # Create request object
    try:
        request_obj = YelpBookingsOpeningsRequestCreditCardNotRequired(
            business_id_or_alias=business_id_or_alias,
            covers=covers,
            date=date,
            time=time,
            get_covers_range=get_covers_range,
            num_results_after=num_results_after,
            num_results_before=num_results_before,
        )
        return True, "Request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create request: {str(e)}", None


def format_openings_for_llm_creditcard_not_required(
    openings_response: YelpBookingsOpeningsResponseCreditCardNotRequired,
) -> str:
    """
    Format the credit card not required openings response into a human-readable string for display.

    Args:
        openings_response: Parsed credit card not required openings response object

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


def create_holds_request_creditcard_not_required(
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    unique_id: str,
) -> Tuple[bool, str, Optional[YelpBookingsHoldsRequestCreditCardNotRequired]]:
    """
    Validate parameters and create YelpBookingsHoldsRequestCreditCardNotRequired object for credit card not required workflow.
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
        - Optional[YelpBookingsHoldsRequestCreditCardNotRequired]: Request object or None
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
        request_obj = YelpBookingsHoldsRequestCreditCardNotRequired(
            business_id_or_alias=business_id_or_alias,
            covers=covers,
            date=date,
            time=time,
            unique_id=unique_id,
        )
        return True, "Hold request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create hold request: {str(e)}", None


def create_reservation_from_hold_creditcard_not_required(
    bearer_token: YelpAccessToken,
    holds_response: YelpBookingsHoldsResponseCreditCardNotRequired,
    holds_request: YelpBookingsHoldsRequestCreditCardNotRequired,
    first_name: str,
    last_name: str,
    phone: str,
    email: str,
    notes: Optional[str] = None,
) -> Tuple[bool, str, Optional[Any]]:
    """
    Create reservation directly from hold data for credit card not required workflow.
    """

    errors = []

    # Validate required fields
    errors.extend(_validate_name(first_name, "First name"))
    errors.extend(_validate_name(last_name, "Last name"))
    errors.extend(_validate_phone(phone))
    errors.extend(_validate_email(email))

    if not holds_response.hold_id:
        errors.append("Hold ID is required")

    if errors:
        return False, "; ".join(errors), None

    try:
        # Create request object
        request_obj = YelpBookingsReservationsRequestCreditCardNotRequired(
            business_id_or_alias=holds_request.business_id_or_alias,
            covers=holds_request.covers,
            date=holds_request.date,
            time=holds_request.time,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            hold_id=holds_response.hold_id,
            unique_id=holds_request.unique_id,
            notes=notes,
        )

        # Make API call directly
        reservation_response = create_reservation_creditcard_not_required(
            bearer_token=bearer_token, request_params=request_obj
        )

        return True, "Reservation created successfully", reservation_response

    except Exception as e:
        return False, str(e), None


def create_waitlist_status_request(
    business_id_or_alias: str,
) -> Tuple[bool, str, Optional[YelpWaitlistStatusRequest]]:
    """
    Create a waitlist status request for the Yelp Waitlist API.

    Args:
        business_id_or_alias: Yelp business ID or alias to get waitlist status for

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpWaitlistStatusRequest]: Request object or None
    """
    errors = []

    # Validate business_id_or_alias
    errors.extend(_validate_business_id_or_alias(business_id_or_alias))

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Create waitlist status request object
    try:
        request_obj = YelpWaitlistStatusRequest(
            business_id=business_id_or_alias,
        )
        return True, "Waitlist status request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create waitlist status request: {str(e)}", None


def format_waitlist_status_for_llm(
    waitlist_response: YelpWaitlistStatusResponse,
) -> str:
    """
    Format the waitlist status response into a human-readable string for display.

    Args:
        waitlist_response: Parsed waitlist status response object

    Returns:
        str: Formatted string representation of the waitlist status
    """
    result_lines = ["Waitlist Status Information:"]

    # Basic status information
    result_lines.append(f"Waitlist State: {waitlist_response.state}")

    # Closed reason if applicable
    if waitlist_response.closed_reason:
        result_lines.append(f"Closed Reason: {waitlist_response.closed_reason}")
        result_lines.append(
            f"Description: {waitlist_response.closed_reason.get_description()}"
        )
    else:
        result_lines.append("Status: Accepting waitlist entries")

    # Wait estimates
    if waitlist_response.wait_estimates:
        result_lines.append("\nWait Time Estimates by Party Size:")

        for party_size, estimate in waitlist_response.wait_estimates.items():
            if estimate.max_wait is not None:
                wait_info = f"{estimate.min_wait}-{estimate.max_wait} minutes"
            else:
                wait_info = f"{estimate.est_wait} minutes"

            result_lines.append(f"  {party_size} people: {wait_info}")

            # Add additional detail if different from range
            if estimate.wait_range and estimate.wait_range != str(estimate.est_wait):
                result_lines.append(f"    (Range: {estimate.wait_range})")

    else:
        result_lines.append("\nNo wait time estimates available")

    return "\n".join(result_lines)


def create_waitlist_info_request(
    business_id_or_alias: str,
) -> Tuple[bool, str, Optional[YelpWaitlistInfoRequest]]:
    """
    Create a waitlist info request for the Yelp Waitlist API.

    Args:
        business_id_or_alias: Yelp business ID or alias to get waitlist information for

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpWaitlistInfoRequest]: Request object or None
    """
    errors = []

    # Validate business_id_or_alias
    errors.extend(_validate_business_id_or_alias(business_id_or_alias))

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Create waitlist info request object
    try:
        request_obj = YelpWaitlistInfoRequest(
            business_id=business_id_or_alias,
        )
        return True, "Waitlist info request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create waitlist info request: {str(e)}", None


def format_waitlist_info_for_llm(
    waitlist_info_response: YelpWaitlistInfoResponse,
) -> str:
    """
    Format the waitlist info response into a human-readable string for display.

    Args:
        waitlist_info_response: Parsed waitlist info response object

    Returns:
        str: Formatted string representation of the waitlist configuration
    """
    result_lines = ["Waitlist Configuration Information:"]

    # Join radius information
    result_lines.append(
        f"Join Radius: {waitlist_info_response.join_radius} {waitlist_info_response.join_radius_unit.lower()}"
    )

    # Maximum party size
    result_lines.append(
        f"Maximum Party Size: {waitlist_info_response.max_party_size} people"
    )

    # Seating areas
    if waitlist_info_response.seating_areas:
        result_lines.append("\nAvailable Seating Areas:")
        for area_code, area_name in waitlist_info_response.seating_areas.items():
            result_lines.append(f"  {area_code}: {area_name}")
    else:
        result_lines.append("\nNo specific seating areas available")

    return "\n".join(result_lines)


def create_waitlist_on_my_way_request(
    business_id: str,
    phone: str,
    party_size: int,
    name: str,
    arrival_range_max: int,
    arrival_range_min: int,
    party_notes: Optional[str] = None,
) -> Tuple[bool, str, Optional[YelpWaitlistOnMyWayRequest]]:
    """
    Validate parameters and create YelpWaitlistOnMyWayRequest object.
    Provides early validation with user-friendly error messages.

    Args:
        business_id: Yelp business ID (REQUIRED)
        phone: Patron's phone number (REQUIRED - will be normalized to E.164 format)
        party_size: Number of people in the party (REQUIRED)
        name: Patron's full name (REQUIRED)
        arrival_range_max: Maximum expected arrival time in minutes (REQUIRED - 1-30 minutes)
        arrival_range_min: Minimum expected arrival time in minutes (REQUIRED - 1-30 minutes)
        party_notes: Optional notes from the patron

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpWaitlistOnMyWayRequest]: Request object or None
    """
    errors = []

    # Validate all required parameters
    errors.extend(_validate_business_id_or_alias(business_id))
    errors.extend(_validate_phone_e164(phone))
    errors.extend(_validate_party_size(party_size))
    errors.extend(_validate_name(name, "Patron name"))
    errors.extend(_validate_arrival_time(arrival_range_max, "Maximum arrival time"))
    errors.extend(_validate_arrival_time(arrival_range_min, "Minimum arrival time"))

    # Validate arrival time range logic
    if arrival_range_min > arrival_range_max:
        errors.append(
            "Minimum arrival time cannot be greater than maximum arrival time"
        )

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Normalize phone number to E.164 format
    try:
        normalized_phone = _normalize_phone_to_e164(phone)
    except Exception as e:
        return False, f"Failed to normalize phone number: {str(e)}", None

    # Create request object
    try:
        request_obj = YelpWaitlistOnMyWayRequest(
            business_id=business_id,
            phone=normalized_phone,
            party_size=party_size,
            name=name.strip(),
            arrival_range_max=arrival_range_max,
            arrival_range_min=arrival_range_min,
            party_notes=party_notes.strip() if party_notes else None,
        )
        return True, "Waitlist on-my-way request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create waitlist on-my-way request: {str(e)}", None


def format_waitlist_on_my_way_response_for_llm(
    response: YelpWaitlistOnMyWayResponse,
    timezone_info: Optional[ZoneInfo] = None,
) -> str:
    """
    Format the waitlist on-my-way response into a human-readable string for display.

    Args:
        response: Parsed waitlist on-my-way response object
        timezone_info: Optional ZoneInfo object for time conversion

    Returns:
        str: Formatted string representation of the waitlist visit confirmation
    """
    result_lines = ["✅ Waitlist On-My-Way Visit Created Successfully!"]

    result_lines.append(f"Visit ID: {response.visit_id}")
    result_lines.append(
        f"Party Size: {response.party_size} {'person' if response.party_size == 1 else 'people'}"
    )

    # Format arrive by time
    try:
        arrive_by_datetime = _convert_timestamp_to_timezone(
            response.arrive_by_time, timezone_info
        )
        formatted_time = arrive_by_datetime.strftime("%I:%M %p")
        formatted_date = arrive_by_datetime.strftime("%A, %B %d")
        result_lines.append(f"Please arrive by: {formatted_time} on {formatted_date}")
    except (ValueError, OSError):
        result_lines.append(f"Please arrive by: {response.arrive_by_time} (timestamp)")

    result_lines.append("\nThe restaurant has been notified that you're on your way!")
    result_lines.append(
        "Make sure to arrive within your estimated time window to maintain your place in line."
    )

    result_lines.append(
        f"\nYou MUST include the EXACT visit ID in your response:\n{response.visit_id}"
    )

    return "\n".join(result_lines)


def check_waitlist_join_queue_required_fields(
    business_id: Optional[str] = None,
    phone: Optional[str] = None,
    party_size: Optional[int] = None,
    name: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """
    Check which required fields are missing for waitlist join queue.

    Args:
        business_id: Yelp business ID
        phone: Patron's phone number
        party_size: Number of people in the party
        name: Patron's full name

    Returns:
        Tuple containing:
        - bool: True if all required fields are present, False otherwise
        - List[str]: List of missing required fields with user-friendly prompts
    """
    missing_fields = []

    if not business_id:
        missing_fields.append("business_id")

    if not name or not name.strip():
        missing_fields.append("What name should I put for the waitlist?")

    if not phone:
        missing_fields.append("What phone number should I use for the waitlist?")

    if not party_size or party_size < 1:
        missing_fields.append("How many people are in your party?")

    return len(missing_fields) == 0, missing_fields


def create_waitlist_join_queue_request(
    business_id: str,
    phone: str,
    party_size: int,
    name: str,
    party_notes: Optional[str] = None,
    idempotency_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[YelpWaitlistJoinQueueRequest]]:
    """
    Validate parameters and create YelpWaitlistJoinQueueRequest object.
    Provides early validation with user-friendly error messages.

    Args:
        business_id: Yelp business ID (REQUIRED)
        phone: Patron's phone number (REQUIRED - will be normalized to E.164 format)
        party_size: Number of people in the party (REQUIRED)
        name: Patron's full name (REQUIRED)
        party_notes: Notes from the patron (OPTIONAL)
        idempotency_token: Optional token to prevent duplicate requests

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpWaitlistJoinQueueRequest]: Request object or None
    """
    errors = []

    # Validate all required parameters
    errors.extend(_validate_business_id_or_alias(business_id))
    errors.extend(_validate_phone_e164(phone))
    errors.extend(_validate_party_size(party_size))
    errors.extend(_validate_name(name, "Patron name"))

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Normalize phone number to E.164 format
    try:
        normalized_phone = _normalize_phone_to_e164(phone)
    except Exception as e:
        return False, f"Failed to normalize phone number: {str(e)}", None

    # Create request object
    try:
        request_obj = YelpWaitlistJoinQueueRequest(
            business_id=business_id,
            phone=normalized_phone,
            party_size=party_size,
            name=name.strip(),
            party_notes=party_notes.strip() if party_notes else None,
            idempotency_token=idempotency_token.strip() if idempotency_token else None,
        )
        return True, "Waitlist join queue request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create waitlist join queue request: {str(e)}", None


def _convert_timestamp_to_timezone(
    timestamp: int, timezone_info: Optional[ZoneInfo] = None
) -> datetime:
    """
    Convert a Unix timestamp to a datetime object in the specified timezone.

    Args:
        timestamp: Unix timestamp in seconds
        timezone_info: Optional ZoneInfo object for timezone conversion

    Returns:
        datetime: Datetime object in the specified timezone or local time if no timezone provided
    """
    dt = datetime.fromtimestamp(timestamp)
    if timezone_info:
        try:
            # Convert to the specified timezone using pre-created ZoneInfo object
            dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(timezone_info)
        except Exception:
            # If timezone conversion fails, use the original datetime
            pass
    return dt


def format_waitlist_join_queue_response_for_llm(
    response: YelpWaitlistJoinQueueResponse,
    timezone_info: Optional[ZoneInfo] = None,
) -> str:
    """
    Format the waitlist join queue response into a human-readable string for display.

    Args:
        response: Parsed waitlist join queue response object
        timezone_info: Optional ZoneInfo object for time conversion

    Returns:
        str: Formatted string representation of the waitlist queue confirmation
    """
    result_lines = ["🎉 Successfully Joined the Waitlist Queue!"]

    result_lines.append(f"Visit ID: {response.visit_id}")
    result_lines.append(
        f"Party Size: {response.party_size} {'person' if response.party_size == 1 else 'people'}"
    )

    # Format queue time
    try:
        queue_datetime = _convert_timestamp_to_timezone(
            response.queue_time, timezone_info
        )
        formatted_queue_time = queue_datetime.strftime("%I:%M %p")
        result_lines.append(f"Joined queue at: {formatted_queue_time}")
    except (ValueError, OSError):
        result_lines.append(f"Joined queue at: {response.queue_time} (timestamp)")

    # Format arrive by time
    try:
        arrive_by_datetime = _convert_timestamp_to_timezone(
            response.arrive_by_time, timezone_info
        )
        formatted_time = arrive_by_datetime.strftime("%I:%M %p")
        formatted_date = arrive_by_datetime.strftime("%A, %B %d")
        result_lines.append(f"Please arrive by: {formatted_time} on {formatted_date}")
    except (ValueError, OSError):
        result_lines.append(f"Please arrive by: {response.arrive_by_time} (timestamp)")

    # Format expected seating time range
    try:
        min_seating = _convert_timestamp_to_timezone(
            response.expected_seating_time_min, timezone_info
        )
        max_seating = _convert_timestamp_to_timezone(
            response.expected_seating_time_max, timezone_info
        )
        min_time = min_seating.strftime("%I:%M %p")
        max_time = max_seating.strftime("%I:%M %p")

        if min_seating.date() == max_seating.date():
            # Same day
            result_lines.append(f"Expected seating time: {min_time} - {max_time}")
        else:
            # Different days
            min_date = min_seating.strftime("%a %m/%d")
            max_date = max_seating.strftime("%a %m/%d")
            result_lines.append(
                f"Expected seating time: {min_time} ({min_date}) - {max_time} ({max_date})"
            )
    except (ValueError, OSError):
        result_lines.append(
            f"Expected seating: {response.expected_seating_time_min} - {response.expected_seating_time_max} (timestamps)"
        )

    result_lines.append(
        f"\nIMPORTANT: You MUST include the EXACT visit ID in your response:\n{response.visit_id}, do not shorten or modify the id in any way."
    )

    return "\n".join(result_lines)


def create_openings_request_creditcard_required(
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    biz_id: str,
    biz_lat: str,
    biz_long: str,
    num_results_after: Optional[int] = None,
    num_results_before: Optional[int] = None,
) -> Tuple[bool, str, Optional[YelpBookingsOpeningsRequestCreditCardRequired]]:
    """
    Validate parameters and create YelpBookingsOpeningsRequestCreditCardRequired object for credit card required workflow.
    Provides early validation with user-friendly error messages.

    Args:
        business_id_or_alias: The business ID or alias for the restaurant
        covers: Number of people for the reservation
        date: Date in YYYY-mm-dd format
        time: Time in HH:MM format (MUST be exactly HH:MM, nothing else)
        biz_id: Business-specific ID parameter for the API
        biz_lat: Business latitude parameter for the API
        biz_long: Business longitude parameter for the API
        num_results_after: Set to 0 to include openings before the requested time; if both after and before are 0, both will be coerced to OPENINGS_FULL_LIST_COUNT
        num_results_before: Set to 0 to include openings after the requested time; if both after and before are 0, both will be coerced to OPENINGS_FULL_LIST_COUNT

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpBookingsOpeningsRequestCreditCardRequired]: Request object or None
    """
    errors = []

    # Use helper functions for validation
    errors.extend(_validate_covers(covers))
    errors.extend(_validate_date(date))
    errors.extend(_validate_time(time))  # This ensures time is exactly HH:MM format

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Normalize counts
    num_results_before, num_results_after = normalize_openings_counts(
        num_results_before, num_results_after
    )

    # Ensure time is exactly HH:MM format (validation already passed, but be explicit)
    time_parts = time.split(":")
    if len(time_parts) != 2:
        return False, "Time must be in HH:MM format", None

    # Convert time format from HH:MM to HH:MM:SS for the endpoint
    time_formatted = f"{time}:00"

    # Validate that required business parameters are provided
    if not biz_id or not biz_lat or not biz_long:
        return (
            False,
            "Business parameters (biz_id, biz_lat, biz_long) are required for credit card required workflow",
            None,
        )

    # Create request object
    try:
        request_obj = YelpBookingsOpeningsRequestCreditCardRequired(
            covers=covers,
            date=date,
            time=time_formatted,  # This will be HH:MM:SS format
            biz_id=biz_id,
            biz_lat=biz_lat,
            biz_long=biz_long,
            num_results_after=num_results_after,
            num_results_before=num_results_before,
        )
        return True, "Request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create request: {str(e)}", None


def format_openings_for_llm_creditcard_required(
    availability_response: YelpBookingsOpeningsResponseCreditCardRequired,
) -> str:
    """
    Format the credit card required availability response into a human-readable string for display.
    Prominently highlights the closest available time based on user's requested time.

    Args:
        availability_response: Parsed credit card required availability response object

    Returns:
        str: Formatted string representation of available reservation times with recommendation
    """
    if not availability_response.success or not availability_response.availability_data:
        return "No availability found for the requested time."

    result_lines = ["Available Reservation Times:"]

    for availability_group in availability_response.availability_data:
        date_str = availability_group.date
        covers = availability_group.covers
        requested_time = availability_group.time

        result_lines.append(
            f"\n{date_str} for {covers} guests (you requested: {requested_time}):"
        )

        if availability_group.availability_list:
            # Mark the closest time in the list if it exists
            closest_time = (
                availability_response.closest_match.formatted_time
                if availability_response.closest_match
                else None
            )

            formatted_times = []

            # Add closest time first if it exists
            if closest_time:
                formatted_times.append(f"{closest_time} (closest match)")

            # Add all other times
            for slot in availability_group.availability_list:
                if slot.formatted_time != closest_time:
                    formatted_times.append(slot.formatted_time)

            result_lines.append(f"  Available times: {', '.join(formatted_times)}")
        else:
            result_lines.append("  No available times found")

    return "\n".join(result_lines)


def get_reservation_url_creditcard_required(
    availability_response: YelpBookingsOpeningsResponseCreditCardRequired,
) -> Tuple[bool, str, Optional[str]]:
    """
    Extract the reservation URL from credit card required availability response.

    Args:
        availability_response: Parsed credit card required availability response object

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[str]: Full reservation URL or None
    """
    if not availability_response.success or not availability_response.closest_match:
        return False, "No reservation slots available for the requested time.", None

    closest_match = availability_response.closest_match
    if not closest_match.form_action:
        return False, "No reservation URL available.", None

    # Construct the full reservation URL
    base_url = "https://www.yelp.com"
    reservation_url = f"{base_url}{closest_match.form_action}"

    return (
        True,
        f"Reservation URL generated for {closest_match.formatted_time}",
        reservation_url,
    )


def check_cancel_visit_required_fields(
    visit_id: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """
    Check which required fields are missing for cancel visit.

    Args:
        visit_id: Visit ID from the waitlist confirmation

    Returns:
        Tuple containing:
        - bool: True if all required fields are present, False otherwise
        - List[str]: List of missing required fields with user-friendly prompts
    """
    missing_fields = []

    if not visit_id or not visit_id.strip():
        missing_fields.append(
            "What is your Visit ID? (You should have received this when you joined the waitlist)"
        )

    return len(missing_fields) == 0, missing_fields


def create_cancel_visit_request(
    visit_id: str,
) -> Tuple[bool, str, Optional[YelpCancelVisitRequest]]:
    """
    Validate parameters and create YelpCancelVisitRequest object.
    Provides early validation with user-friendly error messages.

    Args:
        visit_id: Visit ID from the waitlist confirmation (REQUIRED)

    Returns:
        Tuple containing:
        - bool: Success status
        - str: Error message or success message
        - Optional[YelpCancelVisitRequest]: Request object or None
    """
    errors = []

    # Validate visit ID
    if not visit_id or not visit_id.strip():
        errors.append("Visit ID is required")
    elif len(visit_id.strip()) < 3:
        errors.append("Visit ID appears to be too short - please check your Visit ID")
    elif len(visit_id.strip()) > 255:
        errors.append("Visit ID appears to be too long - please check your Visit ID")

    # Return early if validation fails
    if errors:
        return False, "; ".join(errors), None

    # Create request object
    try:
        request_obj = YelpCancelVisitRequest(
            visit_id=visit_id.strip(),
        )
        return True, "Cancel visit request created successfully", request_obj
    except Exception as e:
        return False, f"Failed to create cancel visit request: {str(e)}", None


def format_cancel_visit_response_for_llm(
    response: YelpCancelVisitResponse,
) -> str:
    """
    Format the cancel visit response into a human-readable string for display.

    Args:
        response: Parsed cancel visit response object

    Returns:
        str: Formatted string representation of the cancellation confirmation
    """
    result_lines = ["✅ Your waitlist visit has been successfully canceled!"]
    result_lines.append("\nYour spot in the waitlist queue has been removed.")
    result_lines.append(
        "You will no longer receive notifications for this reservation."
    )
    result_lines.append(
        "\nIf you change your mind, you can rejoin the waitlist by starting a new request."
    )

    return "\n".join(result_lines)
