import asyncio
import re
from typing import Tuple

from tools.adora_v2_tool._apis import geocode_with_aws_location, geocode_with_google
from tools.adora_v2_tool.classes import DeliveryAddress
from utils.log import logger
from utils.secret import async_get_client_secret_with_fallback


async def get_adora_credentials(account_name: str) -> tuple[str | None, str | None]:
    """Fetch Adora API credentials from AWS Secrets Manager."""
    if not account_name:
        logger.error("[AdoraV2Tool._utils] account_name is missing")
        return None, None

    try:
        name = re.sub(r"[^a-zA-Z0-9]", "", account_name).upper()
        if not name:
            logger.error(
                f"[AdoraV2Tool._utils] account_name '{account_name}' sanitizes to empty string"
            )
            return None, None

        api_key, api_secret = await asyncio.gather(
            async_get_client_secret_with_fallback(f"{name}_ADORA_API_KEY"),
            async_get_client_secret_with_fallback(f"{name}_ADORA_API_SECRET"),
        )
        return api_key, api_secret
    except Exception as e:
        logger.error(f"[AdoraV2Tool._utils] Error: {e}")
        return None, None


async def add_lat_long_to_address(
    delivery_address: DeliveryAddress,
) -> Tuple[bool, str]:
    """Add lat/long to address using AWS Location Service with Google Geocoding fallback."""
    if delivery_address.address == "N/A" or delivery_address.city == "N/A":
        return False, "Ask the user to provide at least a street address and city."

    # Try AWS first, fallback to Google
    result = await geocode_with_aws_location(
        delivery_address
    ) or await geocode_with_google(delivery_address)

    if not result:
        return False, "The address provided is invalid. Please provide a valid address."

    if delivery_address.state == "N/A" or delivery_address.zip == "N/A":
        return (
            False,
            "Please provide your full address with zip code and state information.",
        )

    delivery_address.lat, delivery_address.lng = result
    return True, "Latitude and longitude added to delivery address."


def extract_street_parts(full_address: str) -> Tuple[str, str]:
    """Split '123 Main St' into streetNo='123' and streetName='Main St'."""
    parts = full_address.strip().split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", full_address)
