import time
from typing import Optional

from ddtrace.llmobs.decorators import task

from tools.yelp_credit_card_tool._apis._utils import YELP_API_HOST, connect_yelp_api
from tools.yelp_credit_card_tool.classes import (
    YelpAccessToken,
    YelpBookingsOpeningsRequestCreditCardRequired,
    YelpBookingsOpeningsResponseCreditCardRequired,
    YelpWaitlistInfoResponse,
    YelpWaitlistJoinQueueResponse,
    YelpWaitlistStatusResponse,
)
from utils.log import logger


@task(name="get_waitlist_status")
def get_waitlist_status(
    bearer_token: YelpAccessToken,
    business_id: str,
) -> YelpWaitlistStatusResponse:
    """
    Get waitlist status for a business using the Yelp Waitlist API.

    This endpoint returns waitlist status about a specific business including
    wait estimates for each party size, the closed reason (if applicable),
    and the current state of the waitlist.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id: Encrypted Yelp business identifier

    Returns:
        YelpWaitlistStatusResponse object containing waitlist status information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/businesses/{business_id}/waitlist/status"

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
    )

    if response.status != 200:
        logger.debug(
            f"[YelpCreditCardTool]: get_waitlist_status - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistStatusResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(
            f"[YelpCreditCardTool]: get_waitlist_status - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="get_waitlist_info")
def get_waitlist_info(
    bearer_token: YelpAccessToken,
    business_id: str,
) -> YelpWaitlistInfoResponse:
    """
    Get waitlist information for a business using the Yelp Waitlist API.

    This endpoint returns waitlist configuration information about a specific business
    including the maximum join radius, maximum party size, and seating areas supported
    by the restaurant.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id: Encrypted Yelp business identifier

    Returns:
        YelpWaitlistInfoResponse object containing waitlist configuration information

    Raises:
        Exception: If the API request fails or returns an error
    """
    api_function = f"/v3/businesses/{business_id}/waitlist/info"

    response = connect_yelp_api(
        http_method="GET",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
    )

    if response.status != 200:
        logger.debug(
            f"[YelpCreditCardTool]: get_waitlist_info - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistInfoResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(
            f"[YelpCreditCardTool]: get_waitlist_info - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="join_waitlist_queue")
def join_waitlist_queue(
    bearer_token: YelpAccessToken,
    business_id: str,
    phone: str,
    party_size: int,
    name: str,
    party_notes: Optional[str] = None,
    idempotency_token: Optional[str] = None,
) -> YelpWaitlistJoinQueueResponse:
    """
    Join the waitlist queue for a restaurant using the Yelp Waitlist API.

    This endpoint adds a customer to the restaurant's waitlist queue when there is
    currently a wait. The customer will receive estimated seating times and can
    track their position in the queue.

    Prior to making a call to this endpoint, the restaurant must currently be on a wait,
    or the API caller will receive a 422 CURRENTLY_NO_WAIT response. Enqueuing the first
    party on the waitlist can be achieved by using the Yelp Guest Manager app.

    Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

    Args:
        bearer_token: Yelp bearer token for authentication
        business_id: Encrypted Yelp business identifier
        phone: Patron's phone number in E.164 format (e.g., +19050000000)
        party_size: Number of guests in the party
        name: Patron's name
        party_notes: Notes from the patron (optional)
        idempotency_token: Idempotency token to uniquely identify request (optional)

    Returns:
        YelpWaitlistJoinQueueResponse object containing the queue confirmation details

    Raises:
        Exception: If the API request fails or returns an error. Common error scenarios:
            - 422: Validation errors (phone already in line, no current wait, etc.)
            - 401: Authentication issues
            - 404: Business not found
    """
    api_function = f"/v3/businesses/{business_id}/waitlist/visits"

    payload = {
        "phone": phone,
        "party_size": party_size,
        "name": name,
    }

    # Add optional parameters if provided
    if party_notes is not None:
        payload["party_notes"] = party_notes

    if idempotency_token is not None:
        payload["idempotency_token"] = idempotency_token

    response = connect_yelp_api(
        http_method="POST",
        api_function=api_function,
        api_host=YELP_API_HOST,
        bearer_token=bearer_token,
        payload=payload,
        extra_headers={"Content-Type": "application/json"},
    )

    if response.status != 201:
        logger.debug(
            f"[YelpCreditCardTool]: join_waitlist_queue - Yelp API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
        )
        raise Exception(
            f"Yelp API error: {response.status} {response.reason} {response.decoded_body}"
        )

    try:
        return YelpWaitlistJoinQueueResponse(**response.decoded_body)
    except Exception as e:
        logger.debug(
            f"[YelpCreditCardTool]: join_waitlist_queue - Failed to parse Yelp API response: {str(e)}, Response data: {response.decoded_body}"
        )
        raise Exception(f"Failed to parse Yelp API response: {str(e)}") from e


@task(name="get_openings_creditcard_required")
def get_openings_creditcard_required(
    business_id_or_alias: str,
    request_params: YelpBookingsOpeningsRequestCreditCardRequired,
) -> YelpBookingsOpeningsResponseCreditCardRequired:
    """
    Get available reservation times for restaurants using their open API search endpoint (credit card required workflow).

    This endpoint uses the restaurant's specific availability API that returns time slots
    in their custom format with form actions for direct reservation. This workflow always
    requires completing the reservation on Yelp's website with credit card information.

    Note: This API is not stable and may fail with connection errors. Implements retry logic with 15 attempts.

    Args:
        business_id_or_alias: The business ID or alias for the restaurant
        request_params: OpenApiAvailabilityRequest object containing the search parameters

    Returns:
        OpenApiAvailabilityResponse object containing available reservation times

    Raises:
        Exception: If the API request fails after all retries or returns an error
    """
    # Build query parameters with URL encoded time format
    query_params = {
        "days_before": request_params.days_before,
        "days_after": request_params.days_after,
        "date": request_params.date,
        "time": request_params.time,
        "covers": str(request_params.covers),
        "biz_id": request_params.biz_id,
        "biz_lat": request_params.biz_lat,
        "biz_long": request_params.biz_long,
    }

    # Pass through non-null num_results_* values (0 or positive integers)
    if request_params.num_results_after is not None:
        query_params["num_results_after"] = str(request_params.num_results_after)

    if request_params.num_results_before is not None:
        query_params["num_results_before"] = str(request_params.num_results_before)

    api_function = f"/reservations/{business_id_or_alias}/search_availability"

    extra_headers = {
        "X-Requested-With": "XMLHttpRequest",
    }

    # Retry configuration
    max_retries = 15
    last_exception = None

    for attempt in range(max_retries):
        try:
            # Use the existing connect_yelp_api utility
            response = connect_yelp_api(
                http_method="GET",
                api_function=api_function,
                api_host="www.yelp.com",
                bearer_token=None,  # Open API endpoint doesn't require bearer token
                query_params=query_params,
                extra_headers=extra_headers,
            )

            if response.status != 200:
                logger.debug(
                    f"[YelpCreditCardTool]: get_openings_creditcard_required - Open API returned error: {response.status} {response.reason}, Response body: {response.decoded_body}"
                )
                raise Exception(f"Open API error: {response.status} {response.reason}")

            try:
                return YelpBookingsOpeningsResponseCreditCardRequired(
                    **response.decoded_body
                )
            except Exception as e:
                logger.debug(
                    f"[YelpCreditCardTool]: get_openings_creditcard_required - Failed to parse Open API response: {str(e)}, Response data: {response.decoded_body}"
                )
                raise Exception(f"Failed to parse Open API response: {str(e)}") from e

        except Exception as e:
            last_exception = e
            if attempt == max_retries - 1:
                logger.debug(
                    f"[YelpCreditCardTool]: get_openings_creditcard_required - Open API failed after {attempt + 1} attempts: {e}"
                )
                break

            # Add 0.2 second delay between retries
            logger.debug(
                f"[YelpCreditCardTool]: get_openings_creditcard_required - Open API attempt {attempt + 1} failed ({e}). Retrying in 0.2s..."
            )
            time.sleep(0.2)

    # If we get here, all retries failed
    raise Exception(
        f"Open API failed after {max_retries + 1} attempts. Last error: {last_exception}"
    ) from last_exception
