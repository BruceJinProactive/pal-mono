from typing import Any, Tuple

from ddtrace.llmobs.decorators import task
from geopy.geocoders import Nominatim

from tools.adora_tool.classes import DeliveryAddress
from utils.log import logger


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
    geocoded_loc: Any = geolocator.geocode(geo_payload)
    logger.debug(
        f"[AdoraTool.add_lat_long_to_address] Geocoded location: {bool(geocoded_loc)}"
    )
    if not geocoded_loc:
        logger.debug("[AdoraTool.add_lat_long_to_address] Failed to geocode address.")
        return (
            False,
            "The address that the user provided is invalid. Please provide a valid address. "
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
            f"[AdoraTool.add_lat_long_to_address] Failed to convert address. Delivery address object: {delivery_address}"
        )
        return (
            False,
            "Something went wrong with delivery address conversion. Please try again.",
        )
    delivery_address.lat = geocoded_loc.latitude
    delivery_address.lng = geocoded_loc.longitude
    return (True, "Latitude and longitude added to delivery address.")
