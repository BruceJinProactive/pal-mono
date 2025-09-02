#### NOTE: Most of the logics in this file are borrowed from Adora. ####
import datetime
import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim
from pydantic import ValidationError

from tools.toast_tool._apis import BASE_URL, get_toast_access_token
from tools.toast_tool.classes import (
    DeliveryAddress,
    DiningBehavior,
    ServicePeriod,
    ToastAccessToken,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback, upsert_client_secret

# Constants for better performance and maintainability
_WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_DAY_TO_INDEX = {day: i for i, day in enumerate(_WEEKDAYS)}
VALID_PHONE_PATTERN = r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$"
VALID_EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


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
    return re.match(VALID_PHONE_PATTERN, phone_number) is not None


def is_valid_email(email: str) -> bool:
    return re.match(VALID_EMAIL_PATTERN, email) is not None


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

    try:
        geocoded_loc: Any = geolocator.geocode(geo_payload)
    except GeocoderTimedOut as e:
        logger.error(
            f"[ToastTool.add_lat_long_to_address] Nominatim geocoding timed out: {e}"
        )
        return (
            False,
            "Address lookup service is temporarily unavailable. Please try again in a moment.",
            delivery_address,
        )
    except GeocoderServiceError as e:
        logger.error(
            f"[ToastTool.add_lat_long_to_address] Nominatim geocoding service error: {e}"
        )
        return (
            False,
            "Address lookup service is experiencing issues. Please try again later.",
            delivery_address,
        )
    except Exception as e:
        logger.error(
            f"[ToastTool.add_lat_long_to_address] Unexpected error during geocoding: {e}"
        )
        return (
            False,
            "An error occurred while validating your address. Please try again.",
            delivery_address,
        )
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


def parse_menu(json_data: dict[str, Any], save_to_file: bool = False) -> dict:
    """
    LEGACY CODE. DO NOT USE.
    """
    menu_data = {}

    # Load modifier group and option references for easier lookup
    modifier_groups = json_data.get("modifierGroupReferences", {})
    modifier_options = json_data.get("modifierOptionReferences", {})

    # Iterate through menus
    for menu in json_data.get("menus", []):
        for menu_group in menu.get("menuGroups", []):
            item_group_guid = menu_group["guid"]
            for item in menu_group.get("menuItems", []):
                item_name = item["name"]
                item_guid = item["guid"]
                result_lines = []

                result_lines.append(
                    f"Item name: {item_name} (ItemGroup guid: {item_group_guid}, Item guid: {item_guid})"
                )
                # Check pricing strategy
                pricing_strategy = item.get("pricingStrategy")
                price = item.get("price")
                if pricing_strategy == "BASE_PRICE" and price is not None:
                    result_lines.append(
                        f"{item_name} Base Price (for all sizes such as small, medium, large): {price}"
                    )

                # Process all modifier groups
                modifier_refs = item.get("modifierGroupReferences", [])
                if modifier_refs:
                    for ref_id in modifier_refs:
                        mod_group = modifier_groups.get(str(ref_id))
                        if mod_group:
                            mod_group_name = mod_group["name"]
                            mod_group_guid = mod_group["guid"]
                            result_lines.append(
                                f"\n{item_name} Modifier's optionGroup name: {mod_group_name} (optionGroup guid: {mod_group_guid})"
                            )

                            # List all options in the modifier group
                            for option_ref in mod_group.get(
                                "modifierOptionReferences", []
                            ):
                                option = modifier_options.get(str(option_ref))
                                if option:
                                    option_name = option["name"]
                                    option_price = option.get("price", 0.0)
                                    option_guid = option["guid"]
                                    result_lines.append(
                                        f"  - Option: {option_name}, Price: {option_price} (Modifier item guid: {option_guid})"
                                    )

                menu_data[item_name] = "\n".join(result_lines)

    if save_to_file:
        dirname = (
            f"tools/toast_tool/menus/{datetime.datetime.now().strftime('%Y-%m-%d')}"
        )
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        # Save each item's information to a separate file
        for item_name, information in menu_data.items():
            with open(f"{dirname}/{item_name}.txt", "w") as f:
                f.write(information)

    return menu_data


def _format_dining_option(dining_option: str) -> str:
    """Format dining option behavior string for display."""
    return dining_option.replace("_", " ").title()


def _format_time_range(time_range_dict: Dict[str, str]) -> str:
    """Format time range dictionary to readable string."""
    if (
        not time_range_dict
        or "start" not in time_range_dict
        or "end" not in time_range_dict
    ):
        raise ValueError(f"Invalid time range dictionary: {time_range_dict}")

    return f'{time_range_dict["start"]}–{time_range_dict["end"]}'


def readable_hours(service_period: Dict[str, Any]) -> str:
    """
    Convert service period data to human-readable hours format.

    Args:
        service_period: Dictionary containing service period information

    Returns:
        Formatted string with dining option and hours
    """
    if not service_period or "dayPeriods" not in service_period:
        return ""

    # Get dining option for display
    dining_option = _format_dining_option(
        service_period.get("diningOptionBehavior", "")
    )

    # Group days by their time ranges for efficiency
    time_range_to_days: Dict[str, List[str]] = defaultdict(list)

    for day_period in service_period["dayPeriods"]:
        # Handle both data structures: new format with dayOfWeek and old format with day
        day_name = None
        if "dayOfWeek" in day_period and day_period["dayOfWeek"] is not None:
            day_name = day_period["dayOfWeek"].capitalize()
        elif "day" in day_period:
            day_name = day_period["day"].capitalize()

        if not day_name:
            continue

        # Handle new format with startTime/endTime
        if "startTime" in day_period and "endTime" in day_period:
            start_time = day_period.get("startTime")
            end_time = day_period.get("endTime")
            if start_time is not None and end_time is not None:
                time_range_str = f"{start_time} - {end_time}"
                time_range_to_days[time_range_str].append(day_name)

        # Handle old format with timeRanges
        elif "timeRanges" in day_period:
            for time_range in day_period.get("timeRanges", []):
                time_range_str = _format_time_range(time_range)
                if time_range_str:
                    time_range_to_days[time_range_str].append(day_name)

    if not time_range_to_days:
        return (
            f"{dining_option} Hours: Not available"
            if dining_option
            else "Hours: Not available"
        )

    # Build output
    output_lines = [f"{dining_option} Hours:"] if dining_option else ["Hours:"]

    # Process each time range and group consecutive days
    for time_range_str, days in time_range_to_days.items():
        grouped_days = _group_consecutive_days(days)
        for day_group in grouped_days:
            output_lines.append(f"{day_group}: {time_range_str}")

    return "\n".join(output_lines)


def _group_consecutive_days(days: List[str]) -> List[str]:
    """
    Group consecutive days into ranges (e.g., ['Monday', 'Tuesday'] -> 'Monday–Tuesday').

    Args:
        days: List of day names to group

    Returns:
        List of formatted day ranges
    """
    if not days:
        return []

    if len(days) == 1:
        return days

    # Sort days by weekday order and get their indices
    day_indices = sorted([_DAY_TO_INDEX[day] for day in days if day in _DAY_TO_INDEX])

    if not day_indices:
        return days  # Return original if no valid days found

    # Group consecutive indices
    groups = []
    current_group = [day_indices[0]]

    for i in range(1, len(day_indices)):
        if day_indices[i] == day_indices[i - 1] + 1:
            current_group.append(day_indices[i])
        else:
            groups.append(current_group)
            current_group = [day_indices[i]]
    groups.append(current_group)

    # Format groups back to day names
    formatted_groups = []
    for group in groups:
        if len(group) == 1:
            formatted_groups.append(_WEEKDAYS[group[0]])
        else:
            formatted_groups.append(f"{_WEEKDAYS[group[0]]}–{_WEEKDAYS[group[-1]]}")

    return formatted_groups


def is_within_service_periods(
    timezone_id: str,
    service_periods: List[ServicePeriod],
    dining_behavior: Optional[DiningBehavior] = None,
) -> bool:
    """
    Check if the current time in the given timezone falls within any of the service periods.

    Args:
        timezone_id: The timezone ID (e.g., 'America/Los_Angeles')
        service_periods: List of ServicePeriod objects from Toast API
        dining_behavior: Optional dining behavior to filter by (TAKE_OUT, DELIVERY, etc.)

    Returns:
        bool: True if current time is within service periods, False otherwise
    """
    try:
        # Get current time in the restaurant's timezone
        tz = ZoneInfo(timezone_id)
        current_time = datetime.datetime.now(tz)
        current_day = current_time.strftime("%A")  # Get day name (e.g., 'Monday')
        current_time_str = current_time.strftime("%H:%M")  # Get time as HH:MM
        current_day_upper = current_day.upper()  # Convert once, use multiple times

        logger.debug(
            f"[ToastTool.is_within_service_periods] Checking service periods for {current_day} at {current_time_str} (timezone: {timezone_id})"
        )

        # Collect periods for current day and previous day (for early morning cross-midnight checks)
        current_day_periods = []
        prev_day_periods = []

        # Only check cross-midnight periods if it's early morning (before noon)
        check_cross_midnight = current_time.hour < 12
        prev_day_upper = None
        current_time_obj = None

        if check_cross_midnight:
            prev_day_upper = (
                (current_time - datetime.timedelta(days=1)).strftime("%A").upper()
            )
            # Parse current time once for cross-midnight comparisons
            try:
                current_time_obj = datetime.datetime.strptime(
                    current_time_str, "%H:%M"
                ).time()
            except ValueError as e:
                logger.error(
                    f"[ToastTool.is_within_service_periods] Error parsing current time '{current_time_str}': {e}"
                )
                check_cross_midnight = False

        # Collect day periods that match current day or previous day (for cross-midnight)
        for service_period in service_periods:
            # Skip service periods with no days or wrong dining behavior
            if not service_period.dayPeriods or (
                dining_behavior
                and service_period.diningOptionBehavior != dining_behavior
            ):
                continue

            # Find periods for current day and previous day
            for day_period in service_period.dayPeriods:
                day_name_upper = day_period.day.upper()

                if day_name_upper == current_day_upper:
                    current_day_periods.append(day_period)
                elif check_cross_midnight and day_name_upper == prev_day_upper:
                    prev_day_periods.append(day_period)

        # Check current day periods first
        for day_period in current_day_periods:
            for time_range in day_period.timeRanges:
                try:
                    # For cross-midnight ranges on current day, only match the evening half
                    start_hour = int(time_range.start[:2])
                    end_hour = int(time_range.end[:2])
                    is_cross_midnight = start_hour > end_hour

                    if is_cross_midnight:
                        # Only match if current time is in evening half (>= start time)
                        current_hour = int(current_time_str[:2])
                        if current_hour >= start_hour:
                            logger.debug(
                                f"[ToastTool.is_within_service_periods] Found matching service period: {day_period.day} {time_range.start}-{time_range.end}"
                            )
                            return True
                    elif _is_time_in_range(
                        current_time_str, time_range.start, time_range.end
                    ):
                        logger.debug(
                            f"[ToastTool.is_within_service_periods] Found matching service period: {day_period.day} {time_range.start}-{time_range.end}"
                        )
                        return True
                except (ValueError, IndexError) as e:
                    logger.error(
                        f"[ToastTool.is_within_service_periods] Error parsing time range '{time_range.start}-{time_range.end}' for day {day_period.day}: {e}"
                    )
                    continue

        # Check previous day's cross-midnight periods for early morning hours
        # Cross-midnight periods (e.g., 22:00-02:00) are stored under their start day
        # but also cover the next day's early morning hours
        if check_cross_midnight and current_time_obj:
            for day_period in prev_day_periods:
                for time_range in day_period.timeRanges:
                    try:
                        start_hour = int(time_range.start[:2])
                        end_hour = int(time_range.end[:2])

                        # Check if this is a cross-midnight period (start > end)
                        if start_hour > end_hour:
                            # For cross-midnight periods, only check if current time is before end time (morning half)
                            try:
                                end_time_obj = datetime.datetime.strptime(
                                    time_range.end, "%H:%M"
                                ).time()

                                if current_time_obj <= end_time_obj:
                                    logger.debug(
                                        f"[ToastTool.is_within_service_periods] Found matching cross-midnight period from {day_period.day}: {time_range.start}-{time_range.end}"
                                    )
                                    return True
                            except ValueError as e:
                                logger.error(
                                    f"[ToastTool.is_within_service_periods] Error parsing end time '{time_range.end}' for cross-midnight period {day_period.day}: {e}"
                                )
                                continue
                    except (ValueError, IndexError) as e:
                        logger.error(
                            f"[ToastTool.is_within_service_periods] Error parsing start/end hours for time range '{time_range.start}-{time_range.end}' in previous day period {day_period.day}: {e}"
                        )
                        continue

        logger.debug(
            "[ToastTool.is_within_service_periods] No matching service periods found"
        )
        return False

    except Exception as e:
        logger.error(
            f"[ToastTool.is_within_service_periods] Error checking service periods: {e}"
        )
        return False


def _is_time_in_range(current_time: str, start_time: str, end_time: str) -> bool:
    """
    Check if current time falls within the given time range.

    Args:
        current_time: Current time in HH:MM format
        start_time: Start time in HH:MM format
        end_time: End time in HH:MM format

    Returns:
        bool: True if current time is within range, False otherwise
    """
    try:
        # Parse times
        current = datetime.datetime.strptime(current_time, "%H:%M").time()
        start = datetime.datetime.strptime(start_time, "%H:%M").time()
        end = datetime.datetime.strptime(end_time, "%H:%M").time()

        # Handle cases where end time is past midnight (e.g., 22:00 - 02:00)
        if start <= end:
            # Normal case: start time is before end time on same day
            return start <= current <= end
        else:
            # Cross-midnight case: start time is after end time (spans midnight)
            return current >= start or current <= end

    except ValueError as e:
        logger.error(
            f"[ToastTool._is_time_in_range] Error parsing time range {start_time}-{end_time}: {e}"
        )
        return False


def parse_service_periods(
    service_periods: Union[List[Dict[str, Any]], List[ServicePeriod]],
) -> str:
    """
    Parse multiple service periods into a readable format.

    Args:
        service_periods: List of service period dictionaries or ServicePeriod objects

    Returns:
        Formatted string with all service periods
    """
    if not service_periods:
        return ""

    # Convert ServicePeriod objects to dictionaries if needed
    periods_as_dicts = []
    for period in service_periods:
        if isinstance(period, ServicePeriod):
            periods_as_dicts.append(period.model_dump())
        else:
            periods_as_dicts.append(period)

    # Process all periods - readable_hours now handles invalid data gracefully
    formatted_periods = [
        readable_hours(period)
        for period in periods_as_dicts
        if period  # Only filter out completely None/empty periods
    ]

    # Filter out any empty responses
    formatted_periods = [fp for fp in formatted_periods if fp]
    return "\n".join(formatted_periods)


def get_toast_access_token_from_aws(
    token_api_endpoint: Optional[str] = None,
) -> ToastAccessToken:
    """
    Get a Toast access token from AWS Secrets; refresh via API if missing/expired.
    """
    try:
        # Get the token from AWS secrets
        logger.debug(
            "[ToastTool.get_toast_access_token_from_aws] Getting token from AWS secrets"
        )
        token_json_str = get_client_secret_with_fallback("toast_access_token")
        token_data = json.loads(token_json_str)
        # Reconstruct ToastAccessToken from stored data
        token = ToastAccessToken(**token_data)
    except (
        ValueError,
        KeyError,
        json.JSONDecodeError,
        TypeError,
        ValidationError,
    ) as e:
        # Missing/invalid token in Secrets – fall back to a fresh token
        logger.warning(
            "[ToastTool.get_toast_access_token_from_aws] Stored token invalid; refreshing (error=%s)",
            e.__class__.__name__,
            exc_info=True,
        )
        return refresh_toast_access_token_from_aws(
            token_api_endpoint=token_api_endpoint
        )

    # Check expiration outside the try so refresh errors are not swallowed
    if token.expires_at < datetime.datetime.now(datetime.timezone.utc):
        logger.debug(
            "[ToastTool.get_toast_access_token_from_aws] Token expired, refreshing"
        )
        return refresh_toast_access_token_from_aws(
            token_api_endpoint=token_api_endpoint
        )
    return token


def refresh_toast_access_token_from_aws(
    token_api_endpoint: Optional[str] = None,
) -> ToastAccessToken:
    """
    Refresh Toast access token from API.
    """
    logger.debug(
        "[ToastTool.refresh_toast_access_token_from_aws] Refreshing token from API"
    )
    api_key = get_client_secret_with_fallback("TOAST_CLIENT_ID")
    api_secret = get_client_secret_with_fallback("TOAST_CLIENT_SECRET")
    bearer_token = get_toast_access_token(
        api_key,
        api_secret,
        token_api_endpoint=(token_api_endpoint if token_api_endpoint else BASE_URL),
    )
    if bearer_token is None:
        raise ValueError(
            "[ToastTool.refresh_toast_access_token_from_aws] Failed to get Toast access token"
        )
    # Save the complete ToastAccessToken object to AWS secrets
    token_json = bearer_token.model_dump_json()
    try:
        upsert_client_secret("toast_access_token", token_json)
    except Exception as e:
        logger.warning(
            f"[ToastTool.refresh_toast_access_token_from_aws] Token refreshed but failed to persist to Secrets Manager: {e}"
        )

    return bearer_token
