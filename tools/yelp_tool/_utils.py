import re
from datetime import datetime
from typing import Any, List, Optional, Tuple

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
    YelpWaitlistStatusRequest,
    YelpWaitlistStatusResponse,
)
from utils.log import logger


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
        num_results_after: Set to 0 if user wants to know the openings before the current result, otherwise don't include this field
        num_results_before: Set to 0 if user wants to know the openings after the current result, otherwise don't include this field

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

    # if both are 0, set both to None and log an error
    if num_results_after == 0 and num_results_before == 0:
        logger.warning(
            "num_results_after and num_results_before cannot both be 0, setting both to None"
        )
        num_results_after = None
        num_results_before = None

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
        error_msg = str(e).lower()

        # Determine error prefix based on error type
        if "covers_value_out_of_range" in error_msg:
            error_prefix = f"This restaurant doesn't accept reservations for {holds_request.covers} people."
        elif "invalid_date_time_range" in error_msg:
            error_prefix = f"The date/time {holds_request.date} at {holds_request.time} is invalid."
        else:
            error_prefix = f"Sorry, {holds_request.time} on {holds_request.date} is not available for {holds_request.covers} people."

            # Return simple error message
        return False, error_prefix, None


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
    result_lines.append(f"Business ID: {waitlist_response.business_id}")
    result_lines.append(f"Waitlist State: {waitlist_response.state}")

    # Closed reason if applicable
    if waitlist_response.closed_reason:
        result_lines.append(f"Closed Reason: {waitlist_response.closed_reason}")
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
        num_results_after: Set to 0 if user wants to know the openings before the current result, otherwise don't include this field
        num_results_before: Set to 0 if user wants to know the openings after the current result, otherwise don't include this field

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

    # Validate mutual exclusion of time filters
    if num_results_after == 0 and num_results_before == 0:
        logger.warning(
            "num_results_after and num_results_before cannot both be 0, setting both to None"
        )
        num_results_after = None
        num_results_before = None

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
