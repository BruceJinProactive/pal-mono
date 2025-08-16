from tools.minitable_tool._apis._utils import connect_minitable_api
from utils.log import logger


def search_availability(
    restaurant_id: int,
    search_params: dict,
) -> dict:
    """
    Search for reservation availability for a specific restaurant.

    """
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
