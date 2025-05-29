from typing import Optional

from tools.yelp_tool._apis._utils import (
    YELP_API_HOST,
    YELP_PARTNER_API_HOST,
    connect_yelp_api,
)
from tools.yelp_tool.classes import (
    YelpAccessToken,
    YelpAccessTokenRequest,
    YelpAccessTokenResponse,
    YelpBookingsHoldsRequest,
    YelpBookingsHoldsResponse,
    YelpBookingsOpeningsRequest,
    YelpBookingsOpeningsResponse,
    YelpBookingsReservationsRequest,
    YelpBookingsReservationsResponse,
)
from utils.log import logger


def get_openings(
    bearer_token: YelpAccessToken,
    request_params: YelpBookingsOpeningsRequest,
) -> YelpBookingsOpeningsResponse:
    """
    Get available reservation times for a restaurant using the Yelp Bookings API.

    This endpoint returns available reservation times around the requested timeslot
    and across several days (typically 4 days: day before, current day, and 2 days after).
    Currently, only openings with "credit_card_required": false are returned.

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
        logger.error(f"Yelp API returned error: {response.status} {response.reason}")
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"Yelp API error: {response.status} {response.reason}")

    try:
        return YelpBookingsOpeningsResponse(**response.decoded_body)
    except Exception as e:
        logger.error(f"Failed to parse Yelp API response: {str(e)}")
        logger.error(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def get_yelp_bearer_token(
    request_params: YelpAccessTokenRequest,
) -> YelpAccessTokenResponse:
    """
    Get an access token from the Yelp Partner API using an authorization code.

    This endpoint exchanges an authorization code for an access token that can be used
    to make authorized requests to Yelp APIs on behalf of a business user.

    Args:
        request_params: YelpAccessTokenRequest object containing the token request parameters

    Returns:
        YelpAccessTokenResponse object containing the access token and related information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = "/token/v1"

    payload = {
        "client_id": request_params.client_id,
        "client_secret": request_params.client_secret,
        "code": request_params.code,
        "grant_type": request_params.grant_type,
    }

    if request_params.redirect_uri is not None:
        payload["redirect_uri"] = request_params.redirect_uri

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_PARTNER_API_HOST,
        payload=payload,
    )

    if response.status != 200:
        logger.error(
            f"Yelp Partner API returned error: {response.status} {response.reason}"
        )
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"Yelp Partner API error: {response.status} {response.reason}")

    try:
        return YelpAccessTokenResponse(**response.decoded_body)
    except Exception as e:
        logger.error(f"Failed to parse Yelp Partner API response: {str(e)}")
        logger.error(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp Partner API response: {str(e)}") from e


def create_hold(
    bearer_token: YelpAccessToken,
    request_params: YelpBookingsHoldsRequest,
) -> YelpBookingsHoldsResponse:
    """
    Create a temporary hold on a reservation time slot using the Yelp Bookings API.

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
        logger.error(f"Yelp API returned error: {response.status} {response.reason}")
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"Yelp API error: {response.status} {response.reason}")

    try:
        return YelpBookingsHoldsResponse(**response.decoded_body)
    except Exception as e:
        logger.error(f"Failed to parse Yelp API response: {str(e)}")
        logger.error(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


def create_reservation(
    bearer_token: YelpAccessToken,
    request_params: YelpBookingsReservationsRequest,
) -> YelpBookingsReservationsResponse:
    """
    Create a physical reservation at a restaurant using the Yelp Bookings API.

    This endpoint places a physical reservation at a restaurant with all the information
    provided. This endpoint will take an optional hold id if the partner previously
    placed a hold. If the restaurant requires a credit card hold, you will not be able
    to place a reservation and the API will return an error.

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
        "covers": str(request_params.covers),
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
        logger.error(f"Yelp API returned error: {response.status} {response.reason}")
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"Yelp API error: {response.status} {response.reason}")

    try:
        return YelpBookingsReservationsResponse(**response.decoded_body)
    except Exception as e:
        logger.error(f"Failed to parse Yelp API response: {str(e)}")
        logger.error(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e
