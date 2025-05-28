from typing import Optional

from tools.yelp_tool._apis._utils import connect_yelp_api
from tools.yelp_tool.classes import (
    YelpBookingsOpeningsRequest,
    YelpBookingsOpeningsResponse,
)
from utils.log import logger


def get_openings(
    api_key: str,
    request_params: YelpBookingsOpeningsRequest,
) -> YelpBookingsOpeningsResponse:
    """
    Get available reservation times for a restaurant using the Yelp Bookings API.

    This endpoint returns available reservation times around the requested timeslot
    and across several days (typically 4 days: day before, current day, and 2 days after).
    Currently, only openings with "credit_card_required": false are returned.

    Args:
        api_key: Yelp API key for authentication
        request_params: YelpBookingsOpeningsRequest object containing the search parameters

    Returns:
        YelpBookingsOpeningsResponse object containing available reservation times

    Raises:
        Exception: If the API request fails or returns an error
    """
    # Build the API endpoint with the business ID
    api_function = f"/v3/bookings/{request_params.business_id_or_alias}/openings"

    # Convert request parameters to query parameters
    query_params = {
        "covers": str(request_params.covers),
        "date": request_params.date,
        "time": request_params.time,
    }

    # Add optional get_covers_range parameter if specified
    if request_params.get_covers_range is not None:
        query_params["get_covers_range"] = str(request_params.get_covers_range).lower()

    # Make the API call
    response = connect_yelp_api(
        api_key=api_key,
        api_function=api_function,
        query_params=query_params,
    )

    # Handle the response
    if response.status != 200:
        logger.error(f"Yelp API returned error: {response.status} {response.reason}")
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"Yelp API error: {response.status} {response.reason}")

    # Parse and validate the response using the response model
    try:
        return YelpBookingsOpeningsResponse(**response.decoded_body)
    except Exception as e:
        logger.error(f"Failed to parse Yelp API response: {str(e)}")
        logger.error(f"Response data: {response.decoded_body}")
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e
