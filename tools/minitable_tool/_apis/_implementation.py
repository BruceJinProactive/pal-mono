from tools.minitable_tool._apis._utils import connect_minitable_api
from utils.log import logger


def search_availability(
    restaurant_id: int,
    search_params: dict,
) -> dict:
    """
    Search for reservation availability for a specific restaurant.

    Args:
        restaurant_id: Restaurant ID
        search_params: Search parameters for availability

    Returns:
        Dictionary containing availability data or raises an exception if request fails
    """
    # Construct API endpoint
    api_function = "/api/availability"

    # Create the request body with the required fields
    request_body = {
        "rid": restaurant_id,
        "dateTime": search_params.get("start_date_time"),
        "partySize": search_params.get("party_size"),
    }

    # Call the MiniTable API with POST request
    response = connect_minitable_api(
        api_function=api_function,
        payload=request_body,
    )

    # Handle the response
    if response.status != 200:
        logger.error(
            f"MiniTable API returned error: {response.status} {response.reason}"
        )
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"MiniTable API error: {response.status} {response.reason}")

    # Parse response body
    data = response.decoded_body
    logger.info(f"MiniTable API response: {data}")

    # TODO: Implement proper response parsing
    return {
        "rid": restaurant_id,
        "party_size": search_params.get("party_size"),
        "times_available": [],  # TODO: Extract from actual API response
    }
