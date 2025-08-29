import json
from typing import Optional, Union

from tools.menusifu_tool._apis._utils import connect_menusifu_api, parse_json
from tools.menusifu_tool.classes import (
    MenuResponse,
    OrderCalculationErrorResponse,
    OrderCalculationRequest,
    OrderCalculationResponse,
    OrderGenerationRequest,
    OrderGenerationResponse,
)


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
        # Build API endpoint with /bot path
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


def calculate_order_total(
    access_token: str,
    merchant_id: str,
    order_request: OrderCalculationRequest,
    base_url: str = "assistant.mealkeyway.com",
) -> Union[OrderCalculationResponse, OrderCalculationErrorResponse]:
    """
    Calculate order total for a specific merchant using MenuSifu API.

    Args:
        access_token (str): MenuSifu API access token
        merchant_id (str): The merchant ID to calculate order for
        order_request (OrderCalculationRequest): Order calculation request data
        base_url (str): Base URL for MenuSifu API (default: assistant.mealkeyway.com)

    Returns:
        Union[OrderCalculationResponse, OrderCalculationErrorResponse]:
            Order calculation response or error response

    Raises:
        ValueError: If the API call fails or response validation fails
    """
    try:
        api_endpoint = f"/bot/merchant/{merchant_id}/order/calc"

        # Convert Pydantic model to JSON string for API call (handles Decimal serialization)
        payload = order_request.model_dump_json(by_alias=True)

        # Make API call
        response = connect_menusifu_api(
            http_method="POST",
            access_token=access_token,
            api_endpoint=api_endpoint,
            base_url=base_url,
            payload=payload,
        )

        # Check for API errors (HTTP level)
        if response["status"] != 200:
            error_msg = f"MenuSifu API call failed with status {response['status']} ({response.get('reason', 'Unknown')})"
            if response["decoded_body"]:
                error_msg += f"\nResponse body: {response['decoded_body']}"
            else:
                error_msg += "\nResponse body: (empty)"
            raise ValueError(error_msg)

        # Parse JSON response
        try:
            response_data = json.loads(response["decoded_body"])
        except json.JSONDecodeError:
            raise ValueError(
                f"Invalid JSON response from MenuSifu API: {response['decoded_body']}"
            )

        # Check if response indicates success or business logic error
        if response_data.get("successful", False):
            # Success response - parse as OrderCalculationResponse
            calculation_response = parse_json(
                OrderCalculationResponse, response["decoded_body"]
            )
            if calculation_response is None:
                raise ValueError(
                    "Failed to parse successful response into OrderCalculationResponse model"
                )
            return calculation_response
        else:
            # Error response - parse as OrderCalculationErrorResponse
            error_response = parse_json(
                OrderCalculationErrorResponse, response["decoded_body"]
            )
            if error_response is None:
                raise ValueError(
                    "Failed to parse error response into OrderCalculationErrorResponse model"
                )
            return error_response

    except Exception as e:
        raise ValueError(f"Failed to calculate order total: {str(e)}") from e


def generate_order(
    access_token: str,
    merchant_id: str,
    order_request: OrderGenerationRequest,
    base_url: str = "assistant.mealkeyway.com",
) -> OrderGenerationResponse:
    """
    Generate an order for a specific merchant using MenuSifu API.

    Args:
        access_token (str): MenuSifu API access token
        merchant_id (str): The merchant ID to generate order for
        order_request (OrderGenerationRequest): Order generation request data
        base_url (str): Base URL for MenuSifu API (default: assistant.mealkeyway.com)

    Returns:
        OrderGenerationResponse: Order generation response with payment info and order details

    Raises:
        ValueError: If the API call fails or response validation fails
    """
    try:
        # Build API endpoint - using /bot path like calculation API (301 redirect without it)
        api_endpoint = f"/bot/merchant/{merchant_id}/order/charge"

        # Convert Pydantic model to JSON string for API call (handles Decimal serialization)
        payload = order_request.model_dump_json(by_alias=True)

        # Make API call
        response = connect_menusifu_api(
            http_method="POST",
            access_token=access_token,
            api_endpoint=api_endpoint,
            base_url=base_url,
            payload=payload,
        )

        # Check for API errors (HTTP level)
        if response["status"] != 200:
            error_msg = f"MenuSifu API call failed with status {response['status']} ({response.get('reason', 'Unknown')})"
            if response["decoded_body"]:
                error_msg += f"\nResponse body: {response['decoded_body']}"
            else:
                error_msg += "\nResponse body: (empty)"
            raise ValueError(error_msg)

        # Parse JSON response
        try:
            response_data = json.loads(response["decoded_body"])
        except json.JSONDecodeError:
            raise ValueError(
                f"Invalid JSON response from MenuSifu API: {response['decoded_body']}"
            )

        # Check if response indicates success
        if not response_data.get("successful", False):
            error_msg = f"Order generation failed: {response_data}"
            raise ValueError(error_msg)

        # Parse successful response
        order_response = parse_json(OrderGenerationResponse, response["decoded_body"])
        if order_response is None:
            raise ValueError(
                "Failed to parse response into OrderGenerationResponse model"
            )

        return order_response

    except Exception as e:
        raise ValueError(f"Failed to generate order: {str(e)}") from e
