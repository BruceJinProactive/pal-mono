#### NOTE: Most of the logics in this file are borrowed from Adora. ####
import re
from typing import Any, Tuple

from geopy.geocoders import Nominatim

from tools.toast_tool.classes import DeliveryAddress, DiningBehavior
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


def validate_order_type(order_type: DiningBehavior) -> DiningBehavior:
    if order_type == DiningBehavior.TAKE_OUT or order_type == DiningBehavior.DINE_IN:
        return order_type
    raise ValueError(f"Invalid order type: {order_type}")


def validate_item_modifier_quantity(selections: list) -> None:
    """
    Validate the quantity of item and modifiers in the selections. Each Modifier quantity must match the item quantity.

    Args:
        selections (list): List of item selections.

    Returns:
        None: Raises ValueError if the modifier quantity does not match the item quantity.
    """

    for selection in selections:
        if "modifiers" in selection:
            item_quantity = selection["quantity"]
            for modifier in selection["modifiers"]:
                if modifier["quantity"] != item_quantity:
                    logger.debug(
                        f"[ToastTool.validate_item_modifier_quantity] "
                        f"Modifier quantity {modifier['quantity']} does not match item quantity {item_quantity}."
                    )
                    raise ValueError(
                        f"Modifier {modifier}\n Modifier quantity {modifier['quantity']} does not match item quantity {item_quantity}."
                    )


def add_lat_long_to_address(
    delivery_address: DeliveryAddress,
) -> Tuple[bool, str, DeliveryAddress]:
    """
    Add latitude and longitude to a delivery address. Modifies the delivery address
    object in place.

    Args:
        delivery_address (DeliveryAddress): The delivery address to add latitude and
        longitude to.

    Returns:
        Tuple[bool, str | DeliveryAddress]: A tuple containing a boolean indicating whether the latitude
        and longitude were added successfully, and a string message summarizing the
        result or the modified delivery address object.
    """
    if delivery_address.address == "N/A" or delivery_address.city == "N/A":
        return (
            False,
            "Ask the user to provide at least a street address and city.",
            delivery_address,
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
        "[ToastTool.add_lat_long_to_address] Geolocator payload: " + str(geo_payload)
    )
    geocoded_loc: Any = geolocator.geocode(geo_payload)
    logger.debug(
        f"[ToastTool.add_lat_long_to_address] Geocoded location: {bool(geocoded_loc)}"
    )
    if not geocoded_loc:
        logger.debug("[ToastTool.add_lat_long_to_address] Failed to geocode address.")
        return (
            False,
            "The address provided is invalid. Please provide a valid address. "
            + (
                "Try providing a state and zipcode."
                if delivery_address.state == "N/A" or delivery_address.zip == "N/A"
                else ""
            ),
            delivery_address,
        )

    logger.debug(
        "[ToastTool.add_lat_long_to_address] Nominatim API result: "
        + str(geocoded_loc.latitude)
        + ", "
        + str(geocoded_loc.longitude)
    )

    # auto-populate state and zipcode
    if delivery_address.state == "N/A" or delivery_address.zip == "N/A":
        return (
            False,
            "Please provide your full address with zip code and state information.",
            delivery_address,
        )

    if (
        not delivery_address
        or delivery_address.address == "N/A"
        or delivery_address.city == "N/A"
        or delivery_address.state == "N/A"
        or delivery_address.zip == "N/A"
    ):
        logger.debug(
            "[ToastTool.add_lat_long_to_address] Failed to convert address. "
            f"Delivery address object: {delivery_address}"
        )
        return (
            False,
            "Something went wrong with delivery address conversion. Please try again.",
            delivery_address,
        )
    delivery_address.lat = geocoded_loc.latitude
    delivery_address.lng = geocoded_loc.longitude
    return (True, "Latitude and longitude added to delivery address.", delivery_address)
