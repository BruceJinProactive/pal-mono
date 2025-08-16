from tools.minitable_tool._apis._utils import connect_minitable_api
from utils.log import logger


def search_availability(
    restaurant_id: int,
    search_params: dict,
) -> dict:
    """
    Search for reservation availability for a specific restaurant.

    """
    # Validate required fields
    required_fields = ["start_sec", "party_size"]
    missing_fields = [
        field for field in required_fields if search_params.get(field) is None
    ]

    if missing_fields:
        raise ValueError(f"Missing required fields: {missing_fields}")

    api_function = "/weapp/ai/reserve/availiability/check"

    request_body = {
        "merchant_id": str(restaurant_id),
        "party_size": str(search_params.get("party_size")),
        "slot_time": [
            {
                "start_sec": search_params.get("start_sec", 0),
                "duration_sec": search_params.get("duration_sec", 3600),
            }
        ],
    }

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

    data = response.decoded_body
    logger.debug(f"MiniTable API response: {data}")

    return {
        "party_size": data.get("party_size"),
        "slot_time_availability": data.get("slot_time_availability", []),
    }


def create_reservation(
    restaurant_id: int,
    reservation_params: dict,
) -> dict:
    """
    Create a reservation at a specific restaurant.

    Args:
        restaurant_id: Restaurant ID
        reservation_params: Reservation parameters

    Returns:
        Dictionary containing booking confirmation data or raises exception if request fails
    """
    # Validate required fields
    required_fields = ["telephone", "customer_name", "start_sec", "party_size"]
    missing_fields = [
        field for field in required_fields if not reservation_params.get(field)
    ]

    if missing_fields:
        raise ValueError(f"Missing required fields: {missing_fields}")

    api_function = "/weapp/ai/reserve/create"

    request_body = {
        "telephone": reservation_params.get("telephone"),
        "note": reservation_params.get("note", ""),
        "customer_name": reservation_params.get("customer_name"),
        "slot": {
            "merchant_id": str(restaurant_id),
            "start_sec": str(reservation_params.get("start_sec")),
            "duration_sec": str(reservation_params.get("duration_sec", 3600)),
            "party_size": str(reservation_params.get("party_size")),
        },
    }

    response = connect_minitable_api(
        api_function=api_function,
        payload=request_body,
    )

    if response.status != 200:
        logger.error(
            f"MiniTable API returned error: {response.status} {response.reason}"
        )
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"MiniTable API error: {response.status} {response.reason}")

    data = response.decoded_body
    logger.debug(f"MiniTable API create reservation response: {data}")

    return {
        "booking": data.get("booking", {}),
    }
