from typing import Optional

from tools.menusifu_tool._apis._utils import connect_menusifu_api, parse_json
from tools.menusifu_tool.classes import MenuResponse


def get_merchant_menu(
    access_token: str,
    merchant_id: str,
    base_url: str = "assistant.mealkeyway.com",
) -> MenuResponse:
    """
    Retrieve menu information for a specific merchant from MenuSifu API.

    Args:
        access_token (str): MenuSifu API access token
        merchant_id (str): The merchant ID to get menu for
        base_url (str): Base URL for MenuSifu API (default: assistant.mealkeyway.com)

    Returns:
        MenuResponse: Pydantic model containing the structured menu response

    Raises:
        ValueError: If the API call fails or response validation fails
    """
    try:
        # Build API endpoint
        api_endpoint = f"/bot/merchant/{merchant_id}/menu"

        # Make API call
        response = connect_menusifu_api(
            http_method="GET",
            access_token=access_token,
            api_endpoint=api_endpoint,
            base_url=base_url,
        )

        # Check for API errors
        if response["status"] != 200:
            error_msg = f"MenuSifu API call failed with status {response['status']}: {response['decoded_body']}"
            raise ValueError(error_msg)

        # Validate and return structured response using Pydantic model
        menu_response = parse_json(MenuResponse, response["decoded_body"])
        if menu_response is None:
            raise ValueError("Failed to parse API response into MenuResponse model")

        return menu_response

    except Exception as e:
        raise ValueError(f"Failed to get merchant menu: {str(e)}") from e
