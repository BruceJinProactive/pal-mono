import asyncio
import re
from typing import Tuple, Type

from pydantic import BaseModel

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
) -> Tuple[bool, str | Tuple[float, float]]:
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

    return True, result


def extract_street_parts(full_address: str) -> Tuple[str, str]:
    """Split '123 Main St' into streetNo='123' and streetName='Main St'."""
    parts = full_address.strip().split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", full_address)


def build_extraction_prompt(
    model_class: Type[BaseModel], operation_name: str | None = None
) -> str:
    """
    Build a system prompt for extracting structured data from conversation.

    Args:
        model_class: The Pydantic model class to extract into
        operation_name: Optional name of the operation/function (e.g., "validate_order", "check_address")

    Returns:
        str: System prompt with schema details
    """
    class_name = model_class.__name__
    schema = model_class.model_json_schema()

    # Build operation context
    if operation_name:
        operation_context = (
            f"You are extracting information for the '{operation_name}' operation. "
            f"Analyze the conversation history carefully and extract all relevant details into the {class_name} format."
        )
    else:
        operation_context = f"Extract all relevant information from the conversation history into the {class_name} format."

    instructions = (
        "Important instructions:\n"
        "- Populate ALL required fields based on the conversation\n"
        "- Use the exact field names and types specified in the schema\n"
        "- Apply default values for optional fields when appropriate\n"
        "- Ensure data formats match the schema constraints exactly"
    )

    return (
        f"{operation_context}\n\n"
        f"Required output format: {class_name}\n\n"
        f"Schema specification:\n{schema}\n\n"
        f"{instructions}"
    )


def build_context(menu_context: str, timezone: str | None = None) -> tuple[str, str]:
    """
    Build complete context and user prompt template for order extraction.

    Args:
        menu_context: Menu-related context from query engine
        timezone: Store timezone (defaults to America/Los_Angeles)

    Returns:
        tuple[str, str]: (complete context with datetime, default user prompt template)
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Add current date/time to context for LLM to understand temporal references
    store_tz = timezone or "America/Los_Angeles"
    current_dt_store = datetime.now(ZoneInfo(store_tz))

    current_time_info = (
        f"\n\n<current_datetime>\n"
        f"Current date and time: {current_dt_store.strftime('%A, %B %d, %Y at %I:%M %p')} ({store_tz})\n"
        f"</current_datetime>"
    )

    context = menu_context + current_time_info
    context_template = "{context}\n\n{chat_history}"

    return context, context_template
