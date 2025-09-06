from tools.minitable_tool._apis._utils import connect_minitable_api
from utils.log import logger


def suggest_availability(
    restaurant_id: int,
    party_size: int,
    start_sec: str,
    duration_sec: int = 1800,
) -> dict:
    """
    Check availability for a specific time slot and get suggestions if not available.

    Args:
        restaurant_id: Restaurant ID
        party_size: Number of people for the reservation
        start_sec: Start time in "YYYY-MM-DD HH:MM" format
        duration_sec: Duration in seconds (default 1800 = 30 minutes)

    Returns:
        Dictionary containing availability status and suggested time slots
    """
    api_function = "/weapp/ai/reserve/availability/suggest"

    request_body = {
        "merchant_id": str(restaurant_id),
        "slot_time": {
            "start_sec": start_sec,
            "duration_sec": duration_sec,
        },
        "party_size": party_size,
    }

    logger.debug(
        f"[MiniTable] Checking availability suggest api request: {request_body}"
    )

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
    logger.debug(f"[MiniTable] MiniTable API suggest response: {data}")

    return data


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
    logger.debug(f"[MiniTable] MiniTable API create reservation response: {data}")

    return {
        "booking": data.get("booking", {}),
    }


def create_waitlist(
    merchant_id: str,
    party_size: int,
    telephone: str,
    customer_name: str,
    note: str = "",
) -> dict:
    """
    Create a waitlist entry for a restaurant.

    Args:
        merchant_id: Merchant ID
        party_size: Number of people in the party
        telephone: Customer's phone number
        customer_name: Customer's name
        note: Optional note for the waitlist entry

    Returns:
        Dictionary containing waitlist creation response with waitlist_id, wait_code,
        left_count, and potential business logic failures
    """
    api_function = "/weapp/ai/waitlist/create"

    request_body = {
        "merchant_id": merchant_id,
        "party_size": party_size,
        "telephone": telephone,
        "customer_name": customer_name,
        "note": note,
    }

    logger.debug(f"[MiniTable] Creating waitlist entry with request: {request_body}")

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
    logger.debug(f"[MiniTable] MiniTable API create waitlist response: {data}")

    return data


def check_waitlist_status(merchant_id: str) -> dict:
    """
    Check the current waitlist status for a restaurant.

    Args:
        merchant_id: Merchant ID

    Returns:
        Dictionary containing waitlist status, reason, and wait estimates for different party sizes
    """
    api_function = "/weapp/ai/waitlist/status/check"

    request_body = {
        "merchant_id": merchant_id,
    }

    logger.debug(f"[MiniTable] Checking waitlist status with request: {request_body}")

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
    logger.debug(f"[MiniTable] MiniTable API check waitlist status response: {data}")

    return data
