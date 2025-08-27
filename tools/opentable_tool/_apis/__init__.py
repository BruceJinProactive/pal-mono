import hashlib
import json
import math
from datetime import datetime

from tools.opentable_tool._apis._utils import connect_opentable_api
from tools.opentable_tool.classes import (
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    HttpMethod,
    OpenTableAccessToken,
)
from utils.log import logger


def search_availability(
    bearer_token: OpenTableAccessToken,
    restaurant_id: int,
    search_params: AvailabilitySearchRequest,
) -> AvailabilitySearchResponse:
    """
    Search for reservation availability for a specific restaurant.

    Args:
        bearer_token: OpenTable access token
        restaurant_id: Restaurant ID
        search_params: Search parameters for availability

    Returns:
        AvailabilitySearchResponse object or raises an exception if request fails
    """
    # Construct API endpoint
    api_function = "/dapi/fe/gql?optype=query&opname=RestRefAvailability"

    variables = {
        "forwardDays": 3,
        "restaurantIds": [restaurant_id],
        "date": datetime.fromisoformat(search_params.start_date_time).strftime(
            "%Y-%m-%d"
        ),
        "time": datetime.fromisoformat(search_params.start_date_time).strftime("%H:%M"),
        "partySize": search_params.party_size,
        "databaseRegion": "NA",
        "rid": restaurant_id,
    }

    # Create the request body with deduplicated variables
    request_body = {
        "operationName": "RestRefAvailability",
        "variables": variables,
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "49e1cc30a14ce4449b989941b1c618e1e7df0845188294883ed7f332ab938123",
            }
        },
    }

    # Call the OpenTable API with POST request
    response = connect_opentable_api(
        http_method=HttpMethod.POST,
        bearer_token=bearer_token,
        api_function=api_function,
        payload=request_body,
    )

    # Handle the response
    if response.status != 200:
        logger.error(
            f"OpenTable API returned error: {response.status} {response.reason}"
        )
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"OpenTable API error: {response.status} {response.reason}")

    # Parse response body - ensure it's a dictionary
    data = response.decoded_body
    logger.info(f"OpenTable API response: {data}")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response: {data}")
            data = {}

    if not isinstance(data, dict):
        data = {}

    # Extract relevant data from the response
    dates_available = data.get("availability", {})
    logger.info(f"Dates available: {dates_available}")
    times_available = []
    no_availability_reasons = []

    logger.info(f"Dates available: {dates_available}")
    # For each times_available entry, ensure diningArea attributes are properly handled
    for date in dates_available:
        noTimes = dates_available[date].get("allNoTimesReasons")
        logger.info(f"No times: {noTimes}")
        if noTimes != [] and noTimes is not None:
            no_availability_reasons.extend(noTimes)
        time_slots = dates_available[date].get("timeSlots")
        logger.info(f"Time slots: {time_slots}")
        if time_slots is not None:
            for time_slot in time_slots:
                times_available.append(time_slot.get("dateTime"))
                logger.info(f"Time slot: {time_slot}")
    logger.info(f"Times available: {times_available}")
    logger.info(f"No availability reasons: {no_availability_reasons}")
    # Construct and return the AvailabilitySearchResponse
    return AvailabilitySearchResponse(
        rid=data.get("rid", restaurant_id),
        party_size=data.get("party_size", search_params.party_size),
        times_available=times_available,
        no_availability_reasons=no_availability_reasons,
    )
