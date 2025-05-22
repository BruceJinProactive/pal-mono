import base64
import http.client
import json
from typing import Dict, List, Optional
from urllib.parse import urlencode

from tools.opentable_tool._apis._utils import connect_opentable_api
from tools.opentable_tool.classes import (
    AvailabilityMetadataResponse,
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    CancellationPolicyDetails,
    CreditCardObject,
    EnvironmentType,
    Experience,
    HttpMethod,
    OpenTableAccessToken,
    PhoneObject,
    ReservationRequest,
    ReservationResponse,
    SlotLockRequest,
    SlotLockResponse,
    TableAttribute,
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


def get_availability_metadata(
    bearer_token: OpenTableAccessToken,
    restaurant_id: int,
    use_production: bool = False,
) -> AvailabilityMetadataResponse:
    """
    Get availability metadata for a specific restaurant.

    Args:
        bearer_token: OpenTable access token
        restaurant_id: Restaurant ID
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        AvailabilityMetadataResponse object or raises an exception if request fails
    """
    # Construct API endpoint
    api_function = f"/v2/availability-metadata/{restaurant_id}"

    # Call the OpenTable API
    response = connect_opentable_api(
        http_method=HttpMethod.GET,
        bearer_token=bearer_token,
        api_function=api_function,
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

    # Construct and return the AvailabilityMetadataResponse
    return AvailabilityMetadataResponse(**data)


def get_cancellation_policy(
    bearer_token: OpenTableAccessToken,
    restaurant_id: int,
    cancellation_id: str,
    use_production: bool = False,
) -> CancellationPolicyDetails:
    """
    Get cancellation policy details for a specific reservation.

    Args:
        bearer_token: OpenTable access token
        restaurant_id: Restaurant ID
        cancellation_id: Cancellation policy ID (obtained from the availability search response)
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        CancellationPolicyDetails object or raises an exception if request fails
    """
    # Construct API endpoint
    api_function = f"/v2/cancellation-policies/{restaurant_id}/{cancellation_id}"

    # Call the OpenTable API
    response = connect_opentable_api(
        http_method=HttpMethod.GET,
        bearer_token=bearer_token,
        api_function=api_function,
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

    # Construct and return the CancellationPolicyDetails
    return CancellationPolicyDetails(**data)


def create_slot_lock(
    bearer_token: OpenTableAccessToken,
    restaurant_id: int,
    party_size: int,
    date_time: str,
    reservation_attribute: Optional[TableAttribute] = TableAttribute.DEFAULT,
    experience: Optional[Experience] = None,
    dining_area_id: Optional[int] = None,
    environment: Optional[EnvironmentType] = None,
    use_production: bool = False,
) -> SlotLockResponse:
    """
    Create a slot lock for a reservation at a specific restaurant.

    Args:
        bearer_token: OpenTable access token
        restaurant_id: Restaurant ID
        party_size: Number of people in the reservation party
        date_time: Date and time of the reservation in ISO 8601 format
        reservation_attribute: Type or attribute of the reservation (e.g., default)
        experience: Details about the dining experience (Optional)
        dining_area_id: Identifier for the dining area (Optional)
        environment: Type of environment (e.g., Indoor, Outdoor) (Optional)
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        SlotLockResponse object containing expires_at and reservation_token
    """
    # Construct API endpoint
    api_function = f"/v2/booking/{restaurant_id}/slot_locks"

    # Build request using SlotLockRequest model
    request = SlotLockRequest(
        party_size=party_size,
        date_time=date_time,
        reservation_attribute=reservation_attribute,
        experience=experience,
        dining_area_id=dining_area_id,
        environment=environment,
    )

    # Convert to dictionary for API call
    payload = request.model_dump(exclude_none=True, by_alias=True)

    # Call the OpenTable API
    response = connect_opentable_api(
        http_method=HttpMethod.POST,
        bearer_token=bearer_token,
        api_function=api_function,
        payload=payload,
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

    # Return SlotLockResponse object
    return SlotLockResponse(
        expires_at=data.get("expires_at", ""),
        reservation_token=data.get("reservation_token", ""),
    )


def make_reservation(
    bearer_token: OpenTableAccessToken,
    restaurant_id: int,
    reservation_token: str,
    first_name: str,
    last_name: str,
    email_address: str,
    phone: PhoneObject,
    dining_area_id: int,
    environment: EnvironmentType,
    reservation_attribute: TableAttribute = TableAttribute.DEFAULT,
    special_request: Optional[str] = None,
    restaurant_email_marketing_opt_in: bool = False,
    sms_notifications_opt_in: Optional[bool] = None,
    experience: Optional[Experience] = None,
    credit_card: Optional[CreditCardObject] = None,
    login_name: Optional[str] = None,
    use_production: bool = False,
) -> ReservationResponse:
    """
    Create a reservation at a specific restaurant.

    Args:
        bearer_token: OpenTable access token
        restaurant_id: Restaurant ID
        reservation_token: Token obtained from slot_lock API
        first_name: First name of the guest
        last_name: Last name of the guest
        email_address: Email address of the guest
        phone: Phone details of the guest (with number, country_code, and phone_type)
        dining_area_id: ID of the dining area (required)
        environment: Type of dining environment (e.g., Indoor, Outdoor) (required)
        reservation_attribute: Type of table requested (default, hightop, bar, counter, outdoor)
        special_request: Special requests for the reservation
        restaurant_email_marketing_opt_in: Whether the guest opts in for restaurant marketing emails
        sms_notifications_opt_in: Whether the guest opts in for SMS notifications
        experience: Experience details for the reservation (id, version, party_size_per_price_type, add_ons)
        credit_card: Credit card details (token and last4)
        login_name: Used for concierge/referral details
        use_production: Whether to use production (True) or pre-production (False) environment

    Returns:
        ReservationResponse object containing confirmation details
    """
    # Construct API endpoint
    api_function = f"/v2/booking/{restaurant_id}/reservations"

    # Build request using ReservationRequest model
    request = ReservationRequest(
        reservation_token=reservation_token,
        first_name=first_name,
        last_name=last_name,
        email_address=email_address,
        phone=phone,
        reservation_attribute=reservation_attribute,
        special_request=special_request,
        restaurant_email_marketing_opt_in=restaurant_email_marketing_opt_in,
        sms_notifications_opt_in=sms_notifications_opt_in,
        dining_area_id=dining_area_id,
        environment=environment,
        experience=experience,
        credit_card=credit_card,
        login_name=login_name,
    )

    # Convert to dictionary for API call
    payload = request.model_dump(exclude_none=True, by_alias=True)

    # Call the OpenTable API
    response = connect_opentable_api(
        http_method=HttpMethod.POST,
        bearer_token=bearer_token,
        api_function=api_function,
        payload=payload,
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

    # Return ReservationResponse object
    return ReservationResponse(
        message=data.get("message", ""),
        confirmation_number=data.get("confirmation_number", 0),
        offer_confirmation_number=data.get("offer_confirmation_number", 0),
        date_time=data.get("date_time", ""),
        party_size=data.get("party_size", 0),
        notes=data.get("notes"),  # Allow None as default
        manage_reservation_url=data.get("manage_reservation_url", ""),
    )
