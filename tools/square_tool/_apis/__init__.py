import json
from typing import Optional, Union

from tools.square_tool._apis._utils import connect_square_api, handle_square_response
from tools.square_tool.classes import (
    CatalogListResponse,
    CatalogSearchResponse,
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
