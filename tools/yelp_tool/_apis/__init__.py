from tools.yelp_tool._apis._utils import YELP_API_HOST, connect_yelp_api
from tools.yelp_tool.classes import (
    YelpAccessToken,
    YelpBookingsHoldsRequestCreditCardNotRequired,
    YelpBookingsHoldsResponseCreditCardNotRequired,
    YelpBookingsOpeningsRequestCreditCardNotRequired,
    YelpBookingsOpeningsRequestCreditCardRequired,
    YelpBookingsOpeningsResponseCreditCardNotRequired,
    YelpBookingsOpeningsResponseCreditCardRequired,
    YelpBookingsReservationsRequestCreditCardNotRequired,
    YelpBookingsReservationsResponseCreditCardNotRequired,
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


def get_openings_creditcard_not_required(
    bearer_token: YelpAccessToken,
    request_params: YelpBookingsOpeningsRequestCreditCardNotRequired,
) -> YelpBookingsOpeningsResponseCreditCardNotRequired:
    """
    Get available reservation times for a restaurant using the Yelp Bookings API (credit card not required workflow).

    This endpoint returns available reservation times around the requested timeslot
    and across several days (typically 4 days: day before, current day, and 2 days after).
    This workflow supports direct reservation completion without requiring credit card entry.

    Args:
        bearer_token: Yelp bearer token for authentication
        request_params: YelpBookingsOpeningsRequest object containing the search parameters

    Returns:
        YelpBookingsOpeningsResponse object containing available reservation times

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/bookings/{request_params.business_id_or_alias}/openings"

    query_params = {
        "covers": str(request_params.covers),
        "date": request_params.date,
        "time": request_params.time,
    }

    if request_params.get_covers_range is not None:
        query_params["get_covers_range"] = str(request_params.get_covers_range).lower()

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        query_params=query_params,
    )

    if response.status != 200:
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpBookingsOpeningsResponseCreditCardNotRequired(
            **response.decoded_body
        )
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def create_hold_creditcard_not_required(
    bearer_token: YelpAccessToken,
    request_params: YelpBookingsHoldsRequestCreditCardNotRequired,
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
        request_params: YelpBookingsHoldsRequest object containing the hold parameters

    Returns:
        YelpBookingsHoldsResponse object containing the hold information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/bookings/{request_params.business_id_or_alias}/holds"

    payload = {
        "covers": str(request_params.covers),
        "date": request_params.date,
        "time": request_params.time,
        "unique_id": request_params.unique_id,
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
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpBookingsHoldsResponseCreditCardNotRequired(**response.decoded_body)
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def create_reservation_creditcard_not_required(
    bearer_token: YelpAccessToken,
    request_params: YelpBookingsReservationsRequestCreditCardNotRequired,
) -> YelpBookingsReservationsResponseCreditCardNotRequired:
    """
    Create a physical reservation at a restaurant using the Yelp Bookings API (credit card not required workflow).

    This endpoint places a physical reservation at a restaurant with all the information
    provided. This endpoint will take an optional hold id if the partner previously
    placed a hold. This workflow supports direct reservation completion without credit card requirements.

    In this case, you should use the reserve_url provided in the hold endpoint or the
    opening endpoint to prompt the user for a reservation.

    Note: All parameters are sent as form data in the request body, not as query parameters.
    Additionally, you will receive an error if you don't pass the exact same reservation
    time, date and covers values as you supplied to the Holds endpoint.

    Args:
        bearer_token: Yelp bearer token for authentication
        request_params: YelpBookingsReservationsRequest object containing the reservation parameters

    Returns:
        YelpBookingsReservationsResponse object containing the reservation confirmation

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/bookings/{request_params.business_id_or_alias}/reservations"

    payload = {
        "covers": int(request_params.covers),
        "date": request_params.date,
        "time": request_params.time,
        "first_name": request_params.first_name,
        "last_name": request_params.last_name,
        "phone": request_params.phone,
        "email": request_params.email,
        "hold_id": request_params.hold_id,
        "unique_id": request_params.unique_id,
    }

    if request_params.notes is not None:
        payload["notes"] = request_params.notes

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status != 200:
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpBookingsReservationsResponseCreditCardNotRequired(
            **response.decoded_body
        )
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def get_waitlist_status(
    bearer_token: YelpAccessToken,
    request_params: YelpWaitlistStatusRequest,
) -> YelpWaitlistStatusResponse:
    """
    Get waitlist status for a business using the Yelp Waitlist API.

    This endpoint returns waitlist status about a specific business including
    wait estimates for each party size, the closed reason (if applicable),
    and the current state of the waitlist.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        request_params: YelpWaitlistStatusRequest object containing the business_id

    Returns:
        YelpWaitlistStatusResponse object containing waitlist status information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/businesses/{request_params.business_id}/waitlist/status"

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
    )

    if response.status != 200:
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistStatusResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def get_waitlist_info(
    bearer_token: YelpAccessToken,
    request_params: YelpWaitlistInfoRequest,
) -> YelpWaitlistInfoResponse:
    """
    Get waitlist information for a business using the Yelp Waitlist API.

    This endpoint returns waitlist configuration information about a specific business
    including the maximum join radius, maximum party size, and seating areas supported
    by the restaurant.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        request_params: YelpWaitlistInfoRequest object containing the business_id

    Returns:
        YelpWaitlistInfoResponse object containing waitlist configuration information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/businesses/{request_params.business_id}/waitlist/info"

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
    )

    if response.status != 200:
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistInfoResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def create_waitlist_on_my_way(
    bearer_token: YelpAccessToken,
    request_params: YelpWaitlistOnMyWayRequest,
) -> YelpWaitlistOnMyWayResponse:
    """
    Create a waitlist on-my-way visit at a restaurant using the Yelp Waitlist API.

    This endpoint creates an "on-my-way" visit in the restaurant's waitlist system,
    allowing customers to indicate they are coming to the restaurant and will arrive
    within a specified time range. This helps restaurants manage their waitlist
    and reduce wait times.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.
    The restaurant must allow remote entry and not have any special events or conflicts.

    Args:
        bearer_token: Yelp bearer token for authentication
        request_params: YelpWaitlistOnMyWayRequest object containing the visit parameters

    Returns:
        YelpWaitlistOnMyWayResponse object containing the visit confirmation details

    Raises:
        Exception: If the API request fails or returns an error. Common error scenarios:
            - 409: Visit limit reached (max 9 active on-my-way visits per restaurant)
            - 422: Validation errors (phone already in line, invalid arrival time, etc.)
            - 401: Authentication issues
    """
    api_function = f"/v3/businesses/{request_params.business_id}/waitlist/on-my-way"

    payload = {
        "phone": request_params.phone,
        "party_size": request_params.party_size,
        "name": request_params.name,
        "arrival_range_max": request_params.arrival_range_max,
        "arrival_range_min": request_params.arrival_range_min,
    }

    if request_params.party_notes is not None:
        payload["party_notes"] = request_params.party_notes

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/json"},
    )

    if response.status != 201:
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistOnMyWayResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def join_waitlist_queue(
    bearer_token: YelpAccessToken,
    request_params: YelpWaitlistJoinQueueRequest,
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
        request_params: YelpWaitlistJoinQueueRequest object containing the queue parameters

    Returns:
        YelpWaitlistJoinQueueResponse object containing the queue confirmation details

    Raises:
        Exception: If the API request fails or returns an error. Common error scenarios:
            - 422: Validation errors (phone already in line, no current wait, etc.)
            - 401: Authentication issues
            - 404: Business not found
    """
    api_function = f"/v3/businesses/{request_params.business_id}/waitlist/visits"

    payload = {
        "phone": request_params.phone,
        "party_size": request_params.party_size,
        "name": request_params.name,
    }

    # Add optional parameters if provided
    if request_params.party_notes is not None:
        payload["party_notes"] = request_params.party_notes

    if request_params.idempotency_token is not None:
        payload["idempotency_token"] = request_params.idempotency_token

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/json"},
    )

    if response.status != 201:
        logger.debug(f"Yelp API returned error: {response.status} {response.reason}")
        logger.debug(f"Response body: {response.decoded_body}")
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistJoinQueueResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(f"Failed to parse Yelp API response: {str(e)}")
        logger.debug(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def get_openings_creditcard_required(
    business_id_or_alias: str,
    request_params: YelpBookingsOpeningsRequestCreditCardRequired,
) -> YelpBookingsOpeningsResponseCreditCardRequired:
    """
    Get available reservation times for restaurants using their open API search endpoint (credit card required workflow).

    This endpoint uses the restaurant's specific availability API that returns time slots
    in their custom format with form actions for direct reservation. This workflow always
    requires completing the reservation on Yelp's website with credit card information.

    Note: This API is not stable and may fail with connection errors. Implements retry logic with 6 attempts.

    Args:
        business_id_or_alias: The business ID or alias for the restaurant
        request_params: OpenApiAvailabilityRequest object containing the search parameters

    Returns:
        OpenApiAvailabilityResponse object containing available reservation times

    Raises:
        Exception: If the API request fails after all retries or returns an error
    """
    # Build query parameters with URL encoded time format
    query_params = {
        "days_before": request_params.days_before,
        "days_after": request_params.days_after,
        "date": request_params.date,
        "time": request_params.time,
        "covers": str(request_params.covers),
        "biz_id": request_params.biz_id,
        "biz_lat": request_params.biz_lat,
        "biz_long": request_params.biz_long,
    }

    if request_params.num_results_after == 0:
        query_params["num_results_after"] = "0"

    if request_params.num_results_before == 0:
        query_params["num_results_before"] = "0"

    api_function = f"/reservations/{business_id_or_alias}/search_availability"

    extra_headers = {
        "X-Requested-With": "XMLHttpRequest",
    }

    # Retry configuration
    max_retries = 5  # 6 total attempts (0-5)
    last_exception = None

    for attempt in range(max_retries + 1):  # 0, 1, 2, 3, 4, 5 (6 total attempts)
        try:
            # Use the existing connect_yelp_api utility
            response = connect_yelp_api(
                http_method="GET",
                api_function=api_function,
                api_host="www.yelp.com",
                bearer_token=None,  # Open API endpoint doesn't require bearer token
                query_params=query_params,
                extra_headers=extra_headers,
            )

            if response.status != 200:
                logger.debug(
                    f"Open API returned error: {response.status} {response.reason}"
                )
                logger.debug(f"Response body: {response.decoded_body}")
                raise Exception(f"Open API error: {response.status} {response.reason}")

            try:
                return YelpBookingsOpeningsResponseCreditCardRequired(
                    **response.decoded_body
                )
            except Exception as e:
                logger.debug(f"Failed to parse Open API response: {str(e)}")
                logger.debug(f"Response data: {response.decoded_body}")
                raise Exception(f"Failed to parse Open API response: {str(e)}") from e

        except Exception as e:
            last_exception = e
            if attempt == max_retries:
                logger.debug(f"Open API failed after {attempt + 1} attempts: {e}")
                break

            # Retry immediately without delay
            logger.debug(f"Open API attempt {attempt + 1} failed ({e}).")

    # If we get here, all retries failed
    raise Exception(
        f"Open API failed after {max_retries + 1} attempts. Last error: {last_exception}"
    ) from last_exception
