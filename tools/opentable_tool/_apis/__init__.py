import base64
import http.client
import json
from typing import Dict, Optional
from urllib.parse import urlencode

from tools.opentable_tool._apis._utils import connect_opentable_api
from tools.opentable_tool.classes import (
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    HttpMethod,
    OpenTableAccessToken,
)
from utils.log import logger


def get_opentable_access_token(
    client_id: str,
    client_secret: str,
    use_production: bool = False,
) -> Optional[OpenTableAccessToken]:
    """
    Obtains an access token from the OpenTable Authentication API.

    Args:
        client_id: Your OpenTable API client identifier
        client_secret: Your OpenTable API client secret
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        `OpenTableAccessToken` object if successful, None otherwise
    """
    try:
        # Create basic auth credentials
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        # Set up connection to OpenTable auth server
        host = "oauth.opentable.com" if use_production else "oauth-pp.opentable.com"
        conn = http.client.HTTPSConnection(host)

        # Set headers with basic auth
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

        # Set query parameters
        params = urlencode({"grant_type": "client_credentials"})

        # Make the request
        conn.request("GET", f"/api/v2/oauth/token?{params}", headers=headers)

        # Get the response
        response = conn.getresponse()
        data = response.read().decode()
        conn.close()

        # Parse the response
        if response.status == 200:
            response_data = json.loads(data)
            return OpenTableAccessToken(
                access_token=response_data.get("access_token", ""),
                token_type=response_data.get("token_type", ""),
                expires_in=response_data.get("expires_in", 0),
                scope=response_data.get("scope"),
            )
        else:
            logger.error(
                f"Failed to get OpenTable access token: {response.status} {response.reason}"
            )
            logger.error(f"Response: {data}")
            return None

    except Exception as e:
        logger.error(f"Error getting OpenTable access token: {str(e)}")
        return None


def search_availability(
    bearer_token: OpenTableAccessToken,
    restaurant_id: int,
    search_params: AvailabilitySearchRequest,
    use_production: bool = False,
) -> AvailabilitySearchResponse:
    """
    Search for reservation availability for a specific restaurant.

    Args:
        bearer_token: OpenTable access token
        restaurant_id: Restaurant ID
        search_params: Search parameters for availability
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        AvailabilitySearchResponse object or raises an exception if request fails
    """
    # Construct API endpoint
    api_function = f"/v2/availability/{restaurant_id}"

    # Convert search parameters to query parameters
    # keep aliases & drop Nones in one shot
    query_params: Dict[str, str] = {
        k: (",".join(v) if isinstance(v, list) else str(v))
        for k, v in search_params.model_dump(
            by_alias=True, exclude_none=True, exclude_unset=True
        ).items()
    }

    # Call the OpenTable API
    response = connect_opentable_api(
        http_method=HttpMethod.GET,
        bearer_token=bearer_token,
        api_function=api_function,
        query_params=query_params,
        use_production=use_production,
    )

    # Handle the response
    if response.status != 200:
        logger.error(
            f"OpenTable API returned error: {response.status} {response.reason}"
        )
        logger.error(f"Response body: {response.decoded_body}")
        raise Exception(f"OpenTable API error: {response.status} {response.reason}")

    # Parse response body - ensure it's a dictionary
    data = response.decoded_body
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response: {data}")
            data = {}

    if not isinstance(data, dict):
        data = {}

    # Extract relevant data from the response
    times_available = data.get("times_available", [])

    # For each times_available entry, ensure diningArea attributes are properly handled
    for time_slot in times_available:
        if "availability_types" in time_slot:
            for avail_type in time_slot["availability_types"]:
                if "diningArea" in avail_type and isinstance(
                    avail_type["diningArea"], list
                ):
                    for area in avail_type["diningArea"]:
                        # Ensure attributes is always a list
                        if "attributes" in area and not isinstance(
                            area["attributes"], list
                        ):
                            area["attributes"] = [area["attributes"]]

    # Construct and return the AvailabilitySearchResponse
    return AvailabilitySearchResponse(
        rid=data.get("rid", restaurant_id),
        party_size=data.get("party_size", search_params.party_size),
        times=data.get("times", []),
        times_available=times_available,
        no_availability_reasons=data.get("no_availability_reasons", []),
    )
