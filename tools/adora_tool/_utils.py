import re
from typing import Any, Tuple

from ddtrace.llmobs.decorators import task
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from tools.adora_tool.classes import (
    AdoraOrderType,
    DeliveryAddress,
    ValidateAddressPayload,
)
from utils.log import logger


def format_phone_number(phone_number: str) -> str:
    # Remove non-digit characters
    digits = re.sub(r"\D", "", phone_number)

    # Ensure it has 10 digits (remove US country code if present)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]

    # Validate the number has exactly 10 digits
    if len(digits) != 10:
        return ""

    return digits


def is_valid_phone_number(phone_number: str) -> bool:
    pattern = r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$"
    return re.match(pattern, phone_number) is not None


def is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None


def is_valid_date(date: str) -> bool:
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    return bool(re.match(pattern, date))


def validate_order_type(order_type: str) -> str:
    for member in AdoraOrderType:
        if order_type.lower() == member.lower():
            return member.value
    raise ValueError(f"Invalid order type: {order_type}")


@task
def add_lat_long_to_address(delivery_address: DeliveryAddress) -> Tuple[bool, str]:
    """
    Add latitude and longitude to a delivery address. Modifies the delivery address
    object in place.

    Args:
        delivery_address (DeliveryAddress): The delivery address to add latitude and
        longitude to.

    Returns:
        Tuple[bool, str]: A tuple containing a boolean indicating whether the latitude
        and longitude were added successfully, and a string message summarizing the
        result.
    """
    if delivery_address.address == "N/A" or delivery_address.city == "N/A":
        return (
            False,
            "Ask the user to provide at least a street address and city.",
        )

    # setup Nominatim to convert address to lat long coordinates
    # TODO: Usage limited to 1qps without API key. Upgrade to paid plan when needed.
    # TODO: https://aws.amazon.com/location/
    geolocator = Nominatim(user_agent="pal")

    geo_payload = {
        "street": delivery_address.address,
        "city": delivery_address.city,
        "state": (delivery_address.state if delivery_address.state != "N/A" else ""),
        "country": "USA",
        "postalcode": (delivery_address.zip if delivery_address.zip != "N/A" else ""),
    }
    logger.debug(
        "[AdoraTool.add_lat_long_to_address] Geolocator payload: " + str(geo_payload)
    )

    try:
        geocoded_loc: Any = geolocator.geocode(geo_payload)
    except GeocoderTimedOut as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Nominatim geocoding timed out: {e}"
        )
        return (
            False,
            "Address lookup service is temporarily unavailable. Please try again in a moment.",
        )
    except GeocoderServiceError as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Nominatim geocoding service error: {e}"
        )
        return (
            False,
            "Address lookup service is experiencing issues. Please try again later.",
        )
    except Exception as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Unexpected error during geocoding: {e}"
        )
        return (
            False,
            "An error occurred while validating your address. Please try again.",
        )
    logger.debug(
        f"[AdoraTool.add_lat_long_to_address] Geocoded location: {bool(geocoded_loc)}"
    )
    if not geocoded_loc:
        logger.debug("[AdoraTool.add_lat_long_to_address] Failed to geocode address.")
        return (
            False,
            "The address provided is invalid. Please provide a valid address. "
            + (
                "Try providing a state and zipcode."
                if delivery_address.state == "N/A" or delivery_address.zip == "N/A"
                else ""
            ),
        )

    logger.debug(
        "[AdoraTool.add_lat_long_to_address] Nominatim API result: "
        + str(geocoded_loc.latitude)
        + ", "
        + str(geocoded_loc.longitude)
    )

    # auto-populate state and zipcode
    if delivery_address.state == "N/A" or delivery_address.zip == "N/A":
        return (
            False,
            "Please provide your full address with zip code and state information.",
        )

    if (
        not delivery_address
        or delivery_address.address == "N/A"
        or delivery_address.city == "N/A"
        or delivery_address.state == "N/A"
        or delivery_address.zip == "N/A"
    ):
        logger.debug(
            "[AdoraTool.add_lat_long_to_address] Failed to convert address. "
            f"Delivery address object: {delivery_address}"
        )
        return (
            False,
            "Something went wrong with delivery address conversion. Please try again.",
        )
    delivery_address.lat = geocoded_loc.latitude
    delivery_address.lng = geocoded_loc.longitude
    return (True, "Latitude and longitude added to delivery address.")


def extract_street_parts(full_address: str):
    """
    Naively splits an address like '123 Main St' into:
    - streetNo: '123'
    - streetName: 'Main St'
    """
    parts = full_address.strip().split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", full_address


def build_validate_address_payload(
    store_id: str, canonical_address: DeliveryAddress
) -> Tuple[ValidateAddressPayload | None, str]:
    # Use the address to get the latitude and longitude of the address
    lat_lon_was_added, message = add_lat_long_to_address(canonical_address)  # type: ignore

    if lat_lon_was_added:
        lat, long = canonical_address.lat, canonical_address.lng
        logger.debug(f"Latitude and longitude extracted: {lat}, {long}")
    else:
        return None, message

    street_no, street_name = extract_street_parts(canonical_address.address)

    payload = {
        "storeId": store_id,
        "lat": canonical_address.lat,
        "lng": canonical_address.lng,
        "streetNo": street_no,
        "streetName": street_name,
        "unitApt": canonical_address.extended_address,
        "city": canonical_address.city,
        "state": canonical_address.state,
        "zip": canonical_address.zip,
    }
    return ValidateAddressPayload(**payload), ""
