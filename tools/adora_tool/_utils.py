import re
from typing import Any, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import GoogleV3
from langfuse import observe

from tools.adora_tool.classes import (
    AdoraOrderType,
    DeliveryAddress,
    ValidateAddressPayload,
)
from utils.log import logger
from utils.secret import get_server_secret_with_fallback


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


def geocode_with_google(
    delivery_address: DeliveryAddress,
) -> Tuple[float, float] | None:
    """
    Use Google Geocoding API to geocode an address.

    Args:
        delivery_address: The delivery address to geocode

    Returns:
        Tuple of (latitude, longitude) if successful, None otherwise
    """
    try:
        # Get Google API key from secret manager with environment fallback
        google_api_key = get_server_secret_with_fallback("GOOGLE_GEOCODE_API_KEY")
        geolocator = GoogleV3(api_key=google_api_key)

        # Build address string for Google Geocoding
        address_parts = [delivery_address.address]
        if delivery_address.city != "N/A":
            address_parts.append(delivery_address.city)
        if delivery_address.state != "N/A":
            address_parts.append(delivery_address.state)
        if delivery_address.zip != "N/A":
            address_parts.append(delivery_address.zip)
        address_parts.append("USA")

        geo_address = ", ".join(address_parts)
        logger.debug(
            f"[AdoraTool.add_lat_long_to_address] Google Geocoding address: {geo_address}"
        )

        # Use Google Geocoding API
        geocoded_loc: Any = geolocator.geocode(geo_address)
        if geocoded_loc:
            latitude, longitude = geocoded_loc.latitude, geocoded_loc.longitude
            logger.debug(
                f"[AdoraTool.add_lat_long_to_address] Google Geocoding result: {latitude}, {longitude}"
            )
            return latitude, longitude
        else:
            logger.debug(
                "[AdoraTool.add_lat_long_to_address] No results from Google Geocoding"
            )
            return None

    except GeocoderTimedOut as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Google Geocoding timed out: {e}"
        )
        return None
    except GeocoderServiceError as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Google Geocoding service error: {e}"
        )
        return None
    except Exception as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Unexpected error with Google Geocoding: {e}"
        )
        return None


def geocode_with_aws_location(
    delivery_address: DeliveryAddress,
) -> Tuple[float, float] | None:
    """
    Use AWS geo-places service to geocode an address (new 2024 API).

    Prerequisites:
        - AWS credentials must be configured (IAM role or environment variables)
        - Required IAM permissions: geo-places:Geocode
        - No Place Index setup required!

    Args:
        delivery_address: The delivery address to geocode

    Returns:
        Tuple of (latitude, longitude) if successful, None otherwise
    """
    try:
        # Create AWS geo-places client (new service)
        geo_places_client = boto3.client("geo-places")

        # Build the address text
        address_parts = [delivery_address.address]
        if delivery_address.city != "N/A":
            address_parts.append(delivery_address.city)
        if delivery_address.state != "N/A":
            address_parts.append(delivery_address.state)
        if delivery_address.zip != "N/A":
            address_parts.append(delivery_address.zip)
        address_parts.append("USA")

        address_text = ", ".join(address_parts)

        logger.debug(
            f"[AdoraTool.add_lat_long_to_address] Geocoding address: {address_text}"
        )

        # Use new AWS geo-places geocode API
        response = geo_places_client.geocode(
            QueryText=address_text,
            MaxResults=1,
            QueryComponents={"Country": "USA"},
        )

        if response["ResultItems"] and len(response["ResultItems"]) > 0:
            result_item = response["ResultItems"][0]
            position = result_item["Position"]
            longitude, latitude = (
                position  # AWS geo-places returns [longitude, latitude]
            )

            logger.debug(
                f"[AdoraTool.add_lat_long_to_address] AWS geo-places result: {latitude}, {longitude}"
            )
            return latitude, longitude
        else:
            logger.debug(
                "[AdoraTool.add_lat_long_to_address] No results from AWS geo-places service"
            )
            return None

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] AWS geo-places service client error ({error_code}): {e}"
        )
        return None
    except BotoCoreError as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] AWS geo-places service boto error: {e}"
        )
        return None
    except Exception as e:
        logger.error(
            f"[AdoraTool.add_lat_long_to_address] Unexpected error with AWS geo-places service: {e}"
        )
        return None


@observe()
def add_lat_long_to_address(delivery_address: DeliveryAddress) -> Tuple[bool, str]:
    """
    Add latitude and longitude to a delivery address. Modifies the delivery address
    object in place. Uses AWS Location Service as primary method with Google Geocoding as fallback.

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

    latitude, longitude = None, None

    # Try AWS geo-places service first
    logger.debug(
        "[AdoraTool.add_lat_long_to_address] Attempting geocoding with AWS geo-places service"
    )
    aws_result = geocode_with_aws_location(delivery_address)
    if aws_result:
        latitude, longitude = aws_result
        logger.debug(
            f"[AdoraTool.add_lat_long_to_address] AWS geo-places service success: {latitude}, {longitude}"
        )
    else:
        logger.debug(
            "[AdoraTool.add_lat_long_to_address] AWS geo-places service failed, falling back to Google Geocoding"
        )

        # Fallback to Google Geocoding
        google_result = geocode_with_google(delivery_address)
        if google_result:
            latitude, longitude = google_result
            logger.debug(
                f"[AdoraTool.add_lat_long_to_address] Google Geocoding success: {latitude}, {longitude}"
            )

    # Check if we got results from either service
    if latitude is None or longitude is None:
        logger.debug("[AdoraTool.add_lat_long_to_address] All geocoding methods failed")
        return (
            False,
            "The address provided is invalid. Please provide a valid address. "
            + (
                "Try providing a state and zipcode."
                if delivery_address.state == "N/A" or delivery_address.zip == "N/A"
                else ""
            ),
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

    # Set the latitude and longitude on the delivery address object
    delivery_address.lat = latitude
    delivery_address.lng = longitude
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
