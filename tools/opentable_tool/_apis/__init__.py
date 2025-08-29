import hashlib
import json
import math
from datetime import datetime, timedelta

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

    # Extract relevant data from the new response structure
    availability_data = data.get("data", {}).get("availability", [])
    logger.info(f"Availability data: {availability_data}")
    times_available = []
    no_availability_reasons = []

    # Process each availability entry (there should be one per restaurant)
    for availability_entry in availability_data:
        if not isinstance(availability_entry, dict):
            continue

        # Process availability days
        availability_days = availability_entry.get("availabilityDays", [])
        logger.info(f"Availability days: {availability_days}")

        for day in availability_days:
            if not isinstance(day, dict):
                continue

            # Check for no times reasons
            no_times_reasons = day.get("noTimesReasons", [])
            if no_times_reasons:
                no_availability_reasons.extend(no_times_reasons)
                logger.info(f"No times reasons: {no_times_reasons}")

            # Process time slots
            slots = day.get("slots", [])
            logger.info(f"Slots: {slots}")

            for slot in slots:
                if isinstance(slot, dict) and slot.get("isAvailable", False):
                    # Calculate actual time from timeOffsetMinutes
                    time_offset = slot.get("timeOffsetMinutes", 0)

                    # Calculate the actual time by adding offset to the requested time
                    base_time = datetime.fromisoformat(search_params.start_date_time)
                    actual_time = base_time + timedelta(minutes=time_offset)

                    # Format the time as a string
                    time_string = actual_time.strftime("%Y-%m-%dT%H:%M:%S")
                    times_available.append(time_string)
                    logger.info(
                        f"Available slot at {time_string} (offset: {time_offset} minutes)"
                    )

    logger.info(f"Times available: {times_available}")
    logger.info(f"No availability reasons: {no_availability_reasons}")

    # Construct and return the AvailabilitySearchResponse
    return AvailabilitySearchResponse(
        rid=restaurant_id,  # Use the restaurant_id from the request
        party_size=search_params.party_size,
        times_available=times_available,
        no_availability_reasons=no_availability_reasons,
    )
