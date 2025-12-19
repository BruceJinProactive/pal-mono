import asyncio
import re
from typing import Tuple, Type

from pydantic import BaseModel

from tools.adora_v2_tool._apis import geocode_with_aws_location, geocode_with_google
from tools.adora_v2_tool.classes import BaseDeliveryAddress
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
    delivery_address: BaseDeliveryAddress,
) -> Tuple[bool, str | tuple[float, float]]:
    """Add lat/long to address using AWS Location Service with Google Geocoding fallback.

    Returns:
        Tuple[bool, str | tuple[float, float]]:
            - On success: (True, (lat, lng))
            - On failure: (False, error_message)
    """
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


def build_extraction_prompt(model_class: Type[BaseModel], operation_name: str) -> str:
    """
    Build a system prompt for extracting structured data from conversation.
    Leverages model schema metadata to clearly specify output requirements.

    Args:
        model_class: The Pydantic model class to extract into
        operation_name: Name of the operation/function (e.g., "fulfill_order", "check_address")

    Returns:
        str: System prompt with schema details optimized for LLM compliance
    """
    # Use by_alias=True to get API field names (camelCase) instead of Python names (snake_case)
    schema = model_class.model_json_schema(by_alias=True)
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    # Separate required vs optional fields with their descriptions
    required_list = []
    optional_list = []
    enum_fields = []

    for field_name, field_info in properties.items():
        description = field_info.get("description", "")
        field_type = field_info.get("type", "")

        # Check for enum values
        if "enum" in field_info:
            enum_values = ", ".join(f"'{v}'" for v in field_info["enum"])
            enum_fields.append(f"  • {field_name}: Must be one of [{enum_values}]")

        # Format field info
        field_desc = (
            f"  • {field_name} ({field_type}): {description}"
            if description
            else f"  • {field_name} ({field_type})"
        )

        if field_name in required_fields:
            required_list.append(field_desc)
        else:
            optional_list.append(field_desc)

    # Build structured prompt
    operation_context = (
        f"You are extracting structured data for the '{operation_name}' operation.\n"
        f"Use the information strictly from the conversation history and the provided documents to extract information.\n"
        f"Output must be a valid JSON object matching the schema below."
    )

    field_requirements = "# FIELD REQUIREMENTS:\n"
    if required_list:
        field_requirements += "\n## Required Fields (MUST be populated):\n" + "\n".join(
            required_list
        )
    if optional_list:
        field_requirements += (
            "\n\n## Optional Fields (populate only if explicitly mentioned):\n"
            + "\n".join(optional_list)
        )
    if enum_fields:
        field_requirements += (
            "\n\n## Valid Enum Values (use EXACTLY as shown):\n"
            + "\n".join(enum_fields)
        )

    strict_instructions = (
        "\n# STRICT COMPLIANCE RULES:\n"
        "1. Use EXACT field names from schema (case-sensitive)\n"
        "2. Match data types precisely (string, integer, float, boolean, array, object)\n"
        "3. For enums, use ONLY the exact values listed above\n"
        "4. Required fields: Extract from conversation or use appropriate defaults\n"
        "5. Optional fields: Leave as null/None if not explicitly mentioned\n"
        "6. Do NOT add extra fields not in the schema\n"
        "7. Do NOT fabricate or assume information not stated\n"
        "8. Respect field constraints (max_length, ranges, formats)\n"
        "9. Follow field descriptions as extraction guidance"
    )

    full_schema = f"\n# COMPLETE SCHEMA:\n{schema}"

    return f"{operation_context}\n\n{field_requirements}\n{strict_instructions}\n{full_schema}"


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
