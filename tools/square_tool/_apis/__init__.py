import json
from typing import Optional, Union

from tools.square_tool._apis._utils import connect_square_api, handle_square_response
from utils.ordering.classes import HttpMethod


def list_catalog(
    bearer_token: str,
    cursor: Optional[str] = None,
    types: Optional[str] = None,
    catalog_version: Optional[int] = None,
    use_production: bool = False,
) -> Union[dict, list]:
    """
    List catalog objects from Square's catalog API.

    Args:
        bearer_token (str): The Square access token
        cursor (Optional[str]): The pagination cursor returned in a previous response
        types (Optional[str]): Comma-separated list of object types to retrieve (e.g., "ITEM,CATEGORY")
        catalog_version (Optional[int]): The specific version of the catalog to retrieve
        use_production (bool): Whether to use production (True) or sandbox (False) environment
        square_version (str): Square API version (defaults to 2025-05-21)

    Returns:
        Union[dict, list]: The catalog list response from Square API

    Raises:
        ValueError: If the API call fails
    """
    try:
        # Build query parameters
        query_params = {}
        if cursor:
            query_params["cursor"] = cursor
        if types:
            query_params["types"] = types
        if catalog_version:
            query_params["catalog_version"] = catalog_version

        response = connect_square_api(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/v2/catalog/list",
            query_params=query_params if query_params else None,
            use_production=use_production,
        )

        # Return raw response as dict since we don't have specific response models yet
        result = handle_square_response(response)
        if isinstance(result, str):
            return json.loads(result)
        return result

    except Exception as e:
        raise ValueError(f"Failed to list catalog: {str(e)}") from e
