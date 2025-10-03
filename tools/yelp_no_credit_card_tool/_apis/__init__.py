from ddtrace.llmobs.decorators import task

from tools.yelp_no_credit_card_tool._apis._utils import YELP_API_HOST, connect_yelp_api
from tools.yelp_no_credit_card_tool.classes import (
    YelpAccessToken,
    YelpBookingsHoldsResponseCreditCardNotRequired,
    YelpBookingsOpeningsResponseCreditCardNotRequired,
    YelpBookingsReservationsResponseCreditCardNotRequired,
    YelpWaitlistJoinQueueResponse,
    YelpWaitlistStatusResponse,
)
from utils.log import logger


@task(name="get_openings_creditcard_not_required")
def get_openings_creditcard_not_required(
    bearer_token: YelpAccessToken,
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
) -> YelpBookingsOpeningsResponseCreditCardNotRequired:
    """
    Get available reservation times for a restaurant using the Yelp Bookings API (credit card not required workflow).

    This endpoint returns available reservation times around the requested timeslot
    and across several days (typically 4 days: day before, current day, and 2 days after).
    This workflow supports direct reservation completion without requiring credit card information.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id_or_alias: The business ID or alias for the restaurant
        covers: Number of people for the reservation (1-10)
        date: Desired reservation date in YYYY-MM-DD format
        time: Desired reservation time in HH:MM format (24-hour)

    Returns:
        YelpBookingsOpeningsResponseCreditCardNotRequired object containing available reservation times

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/bookings/{business_id_or_alias}/openings"

    query_params = {
        "covers": str(covers),
        "date": date,
        "time": time,
    }

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        query_params=query_params,
    )

    if response.status != 200:
        logger.debug(
            f"[YelpNoCreditCardTool]: get_openings_creditcard_not_required - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: status {response.status}; {response.reason}; {response.decoded_body}"
        )

    try:
        return YelpBookingsOpeningsResponseCreditCardNotRequired(
            **response.decoded_body
        )
    except Exception as e:
        logger.debug(
            f"[YelpNoCreditCardTool]: get_openings_creditcard_not_required - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="create_hold_creditcard_not_required")
def create_hold_creditcard_not_required(
    bearer_token: YelpAccessToken,
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    unique_id: str,
) -> YelpBookingsHoldsResponseCreditCardNotRequired:
    """
    Create a temporary hold on a reservation time slot using the Yelp Bookings API (credit card not required workflow).

    This endpoint places a temporary hold on the requested time slot so that the partner
    can request all the required reservation information from the user. Holds are only
    valid for 5 minutes and you must use the hold_id returned from this endpoint to
    place the reservation or you will get a conflict.

    Note: All parameters are sent as form data in the request body, not as query parameters.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id_or_alias: The business ID or alias for the restaurant
        covers: Number of people for the reservation (1-10)
        date: Desired reservation date in YYYY-MM-DD format
        time: Desired reservation time in HH:MM format (24-hour)
        unique_id: User's device id or unique user id to help tie together actions of the user on the API

    Returns:
        YelpBookingsHoldsResponseCreditCardNotRequired object containing the hold information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/bookings/{business_id_or_alias}/holds"

    payload = {
        "covers": str(covers),
        "date": date,
        "time": time,
        "unique_id": unique_id,
    }

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status != 200:
        logger.debug(
            f"[YelpNoCreditCardTool]: create_hold_creditcard_not_required - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: status {response.status}; {response.reason}; {response.decoded_body}"
        )

    try:
        return YelpBookingsHoldsResponseCreditCardNotRequired(**response.decoded_body)
    except Exception as e:
        logger.debug(
            f"[YelpNoCreditCardTool]: create_hold_creditcard_not_required - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="create_reservation_creditcard_not_required")
def create_reservation_creditcard_not_required(
    bearer_token: YelpAccessToken,
    business_id_or_alias: str,
    covers: int,
    date: str,
    time: str,
    first_name: str,
    last_name: str,
    phone: str,
    email: str,
    hold_id: str,
    unique_id: str,
    notes: str = "",
) -> YelpBookingsReservationsResponseCreditCardNotRequired:
    """
    Create a physical reservation at a restaurant using the Yelp Bookings API (credit card not required workflow).

    This endpoint places a physical reservation at a restaurant with all the information
    provided. This endpoint will take an optional hold id if the partner previously
    placed a hold. This workflow supports direct reservation completion without credit card requirements.

    Note: All parameters are sent as form data in the request body, not as query parameters.
    Additionally, you will receive an error if you don't pass the exact same reservation
    time, date and covers values as you supplied to the Holds endpoint.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id_or_alias: The business ID or alias for the restaurant
        covers: Number of people for the reservation (1-10)
        date: Desired reservation date in YYYY-MM-DD format
        time: Desired reservation time in HH:MM format (24-hour)
        first_name: The first name of the person making the reservation
        last_name: The last name of the person making the reservation
        phone: The phone number to attach to the reservation
        email: The email to attach to the reservation
        hold_id: The Hold ID returned from the Holds endpoint
        unique_id: User's device id or unique user id to help tie together actions of the user on the API
        notes: Additional party notes for the reservation (optional)

    Returns:
        YelpBookingsReservationsResponseCreditCardNotRequired object containing the reservation confirmation

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/bookings/{business_id_or_alias}/reservations"

    payload = {
        "covers": int(covers),
        "date": date,
        "time": time,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email,
        "hold_id": hold_id,
        "unique_id": unique_id,
    }

    if notes:
        payload["notes"] = notes

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status != 200:
        logger.debug(
            f"[YelpNoCreditCardTool]: create_reservation_creditcard_not_required - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: status {response.status}; {response.reason}; {response.decoded_body}"
        )

    try:
        return YelpBookingsReservationsResponseCreditCardNotRequired(
            **response.decoded_body
        )
    except Exception as e:
        logger.debug(
            f"[YelpNoCreditCardTool]: create_reservation_creditcard_not_required - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="get_waitlist_status")
def get_waitlist_status(
    bearer_token: YelpAccessToken,
    business_id: str,
) -> YelpWaitlistStatusResponse:
    """
    Get waitlist status for a business using the Yelp Waitlist API.

    This endpoint returns waitlist status about a specific business including
    wait estimates for each party size, the closed reason (if applicable),
    and the current state of the waitlist.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id: Encrypted Yelp business identifier

    Returns:
        YelpWaitlistStatusResponse object containing waitlist status information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/businesses/{business_id}/waitlist/status"

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
    )

    if response.status != 200:
        logger.debug(
            f"[YelpNoCreditCardTool]: get_waitlist_status - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: status {response.status}; {response.reason}; {response.decoded_body}"
        )

    try:
        return YelpWaitlistStatusResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(
            f"[YelpNoCreditCardTool]: get_waitlist_status - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="join_waitlist_queue")
def join_waitlist_queue(
    bearer_token: YelpAccessToken,
    business_id: str,
    phone: str,
    party_size: int,
    name: str,
    party_notes: str = "",
) -> YelpWaitlistJoinQueueResponse:
    """
    Join the waitlist queue for a restaurant using the Yelp Waitlist API.

    This endpoint adds a customer to the restaurant's waitlist queue when there is
    currently a wait. The customer will receive estimated seating times and can
    track their position in the queue.

    Prior to making a call to this endpoint, the restaurant must currently be on a wait,
    or the API caller will receive a 422 CURRENTLY_NO_WAIT response. Enqueuing the first
    party on the waitlist can be achieved by using the Yelp Guest Manager app.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id: Encrypted Yelp business identifier
        phone: Patron's phone number in E.164 format (e.g., +19050000000)
        party_size: Number of guests in the party
        name: Patron's name
        party_notes: Notes from the patron (optional)

    Returns:
        YelpWaitlistJoinQueueResponse object containing the queue confirmation details

    Raises:
        Exception: If the API request fails or returns an error. Common error scenarios:
            - 422: Validation errors (phone already in line, no current wait, etc.)
            - 401: Authentication issues
            - 404: Business not found
    """
    api_function = f"/v3/businesses/{business_id}/waitlist/visits"

    payload = {
        "phone": phone,
        "party_size": party_size,
        "name": name,
    }

    if party_notes:
        payload["party_notes"] = party_notes

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/json"},
    )

    if response.status != 201:
        logger.debug(
            f"[YelpNoCreditCardTool]: join_waitlist_queue - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: status {response.status}; {response.reason}; {response.decoded_body}"
        )

    try:
        return YelpWaitlistJoinQueueResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(
            f"[YelpNoCreditCardTool]: join_waitlist_queue - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e
