import json
from typing import Optional, Union

from tools.square_tool._apis._utils import connect_square_api, handle_square_response
from tools.square_tool.classes import (
    CatalogListResponse,
    CatalogSearchResponse,
    CreateOrderInput,
    CreateOrderResponse,
    CreatePaymentLinkInput,
    CreatePaymentLinkResponse,
    GetCatalogObjectInput,
    GetCatalogObjectResponse,
    ListCatalogInput,
    SearchCatalogInput,
    SquareAccessToken,
)
from utils.ordering.classes import HttpMethod


def list_catalog(
    access_token: SquareAccessToken,
    input_data: ListCatalogInput,
) -> CatalogListResponse:
    """
    List catalog objects from Square's catalog API.

    Args:
        access_token (SquareAccessToken): The Square access token model containing the token and type
        input_data (ListCatalogInput): Pydantic model containing all input parameters

    Returns:
        CatalogListResponse: Pydantic model containing the structured catalog response

    Raises:
        ValueError: If the API call fails
    """
    try:
        # Build query parameters from input model
        query_params = {}
        if input_data.cursor:
            query_params["cursor"] = input_data.cursor
        if input_data.types:
            query_params["types"] = input_data.types
        if input_data.catalog_version:
            query_params["catalog_version"] = input_data.catalog_version

        response = connect_square_api(
            http_method=HttpMethod.GET,
            access_token=access_token,
            api_function="/v2/catalog/list",
            query_params=query_params if query_params else None,
            use_production=input_data.use_production,
        )

        # Handle response and parse with Pydantic
        result = handle_square_response(response)
        if isinstance(result, str):
            result = json.loads(result)

        # Return structured response using Pydantic model
        return CatalogListResponse(**result)

    except Exception as e:
        raise ValueError(f"Failed to list catalog: {str(e)}") from e


def search_catalog(
    access_token: SquareAccessToken,
    input_data: SearchCatalogInput,
) -> CatalogSearchResponse:
    """
    Search catalog objects from Square's catalog API.

    Args:
        access_token (SquareAccessToken): The Square access token model containing the token and type
        input_data (SearchCatalogInput): Pydantic model containing all search parameters

    Returns:
        CatalogSearchResponse: Pydantic model containing the structured search response

    Raises:
        ValueError: If the API call fails
    """
    try:
        # Build request payload from input model
        payload = {}

        # Add query (required)
        payload["query"] = input_data.query.model_dump()

        # Add optional parameters
        if input_data.object_types:
            payload["object_types"] = input_data.object_types
        if input_data.include_related_objects is not None:
            payload["include_related_objects"] = input_data.include_related_objects
        if input_data.include_category_path_to_root is not None:
            payload["include_category_path_to_root"] = (
                input_data.include_category_path_to_root
            )
        if input_data.limit is not None:
            payload["limit"] = input_data.limit

        response = connect_square_api(
            http_method=HttpMethod.POST,
            access_token=access_token,
            api_function="/v2/catalog/search",
            payload=payload,
            use_production=input_data.use_production,
        )

        # Handle response and parse with Pydantic
        result = handle_square_response(response)
        if isinstance(result, str):
            result = json.loads(result)

        # Return structured response using Pydantic model
        return CatalogSearchResponse(**result)

    except Exception as e:
        raise ValueError(f"Failed to search catalog: {str(e)}") from e


def create_order(
    access_token: SquareAccessToken,
    input_data: CreateOrderInput,
) -> CreateOrderResponse:
    """
    Create a new order using Square's Orders API.

    Args:
        access_token (SquareAccessToken): The Square access token model containing the token and type
        input_data (CreateOrderInput): Pydantic model containing the order data and optional idempotency key

    Returns:
        CreateOrderResponse: Pydantic model containing the created order response

    Raises:
        ValueError: If the API call fails
    """
    try:
        # Build request payload from input model
        payload = {}

        # Add order (required)
        payload["order"] = input_data.order.model_dump(exclude_none=True)

        # Add idempotency key if provided
        if input_data.idempotency_key:
            payload["idempotency_key"] = input_data.idempotency_key

        response = connect_square_api(
            http_method=HttpMethod.POST,
            access_token=access_token,
            api_function="/v2/orders",
            payload=payload,
            use_production=input_data.use_production,
        )

        # Handle response and parse with Pydantic
        result = handle_square_response(response)
        if isinstance(result, str):
            result = json.loads(result)

        # Return structured response using Pydantic model
        return CreateOrderResponse(**result)

    except Exception as e:
        raise ValueError(f"Failed to create order: {str(e)}") from e


def create_payment_link(
    access_token: SquareAccessToken,
    input_data: CreatePaymentLinkInput,
) -> CreatePaymentLinkResponse:
    """
    Create a Square-hosted checkout page.

    Applications can share the resulting payment link with their buyer to pay for goods and services.

    Args:
        access_token (SquareAccessToken): The Square access token model containing the token and type
        input_data (CreatePaymentLinkInput): Pydantic model containing the payment link data

    Returns:
        CreatePaymentLinkResponse: Pydantic model containing the created payment link response

    Raises:
        ValueError: If the API call fails
    """
    try:
        # Build request payload from input model
        payload = {}

        # Add idempotency key if provided
        if input_data.idempotency_key:
            payload["idempotency_key"] = input_data.idempotency_key

        # Add description if provided
        if input_data.description:
            payload["description"] = input_data.description

        # Add quick_pay if provided
        if input_data.quick_pay:
            payload["quick_pay"] = input_data.quick_pay.model_dump(exclude_none=True)

        # Add order if provided
        if input_data.order:
            # Exclude read-only fields when serializing the order for payment link creation
            # Based on Square API documentation - all fields marked as "Read only"
            order_data = input_data.order.model_dump(
                exclude_none=True,
                exclude={
                    # System-managed fields
                    "id",
                    "created_at",
                    "updated_at",
                    "closed_at",
                    "state",
                    "version",
                    # Money calculation fields (read-only)
                    "total_money",
                    "total_tax_money",
                    "total_discount_money",
                    "total_tip_money",
                    "total_service_charge_money",
                    "net_amount_due_money",
                    # Order amounts and adjustments (read-only)
                    "net_amounts",
                    "return_amounts",
                    "rounding_adjustment",
                    # Transaction-related fields (read-only)
                    "returns",
                    "tenders",
                    "refunds",
                    "rewards",
                },
            )

            # Manually clean read-only fields from line items
            if "line_items" in order_data and order_data["line_items"]:
                line_item_readonly_fields = {
                    "uid",
                    "variation_total_price_money",
                    "total_money",
                    "total_tax_money",
                    "total_discount_money",
                    "total_service_charge_money",
                    "gross_sales_money",
                }

                for line_item in order_data["line_items"]:
                    for field in line_item_readonly_fields:
                        line_item.pop(field, None)

            payload["order"] = order_data

        # Add checkout_options if provided
        if input_data.checkout_options:
            payload["checkout_options"] = input_data.checkout_options.model_dump(
                exclude_none=True
            )

        # Add pre_populated_data if provided
        if input_data.pre_populated_data:
            payload["pre_populated_data"] = input_data.pre_populated_data.model_dump(
                exclude_none=True
            )

        # Add payment_note if provided
        if input_data.payment_note:
            payload["payment_note"] = input_data.payment_note

        response = connect_square_api(
            http_method=HttpMethod.POST,
            access_token=access_token,
            api_function="/v2/online-checkout/payment-links",
            payload=payload,
            use_production=input_data.use_production,
        )

        # Handle response and parse with Pydantic
        result = handle_square_response(response)
        if isinstance(result, str):
            result = json.loads(result)

        # Return structured response using Pydantic model
        return CreatePaymentLinkResponse(**result)

    except Exception as e:
        raise ValueError(f"Failed to create payment link: {str(e)}") from e


def get_catalog_object(
    access_token: SquareAccessToken,
    input_data: GetCatalogObjectInput,
) -> GetCatalogObjectResponse:
    """
    Retrieve a single catalog object from Square's catalog API.

    Args:
        access_token (SquareAccessToken): The Square access token model containing the token and type
        input_data (GetCatalogObjectInput): Pydantic model containing the object ID and optional parameters

    Returns:
        GetCatalogObjectResponse: Pydantic model containing the catalog object and related objects

    Raises:
        ValueError: If the API call fails
    """
    try:
        # Build query parameters from input model
        query_params = {}
        if input_data.catalog_version:
            query_params["catalog_version"] = input_data.catalog_version
        if input_data.include_category_path_to_root is not None:
            query_params["include_category_path_to_root"] = (
                input_data.include_category_path_to_root
            )
        if input_data.include_related_objects is not None:
            query_params["include_related_objects"] = input_data.include_related_objects

        response = connect_square_api(
            http_method=HttpMethod.GET,
            access_token=access_token,
            api_function=f"/v2/catalog/object/{input_data.object_id}",
            query_params=query_params if query_params else None,
            use_production=input_data.use_production,
        )

        # Handle response and parse with Pydantic
        result = handle_square_response(response)
        if isinstance(result, str):
            result = json.loads(result)

        # Return structured response using Pydantic model
        return GetCatalogObjectResponse(**result)

    except Exception as e:
        raise ValueError(f"Failed to get catalog object: {str(e)}") from e
