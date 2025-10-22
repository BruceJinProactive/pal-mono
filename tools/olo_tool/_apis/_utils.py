import base64
import hashlib
import hmac
import http.client
import json
import random
import urllib.parse
from email.utils import formatdate
from typing import Type, TypeVar, Union

from tools.olo_tool.classes import OloAccessToken, OloSignedToken
from tools.utils.ordering._utils import connect_order_hub
from tools.utils.ordering.classes import ApiProvider, GenericHubResponse, HttpMethod
from utils.log import logger

T = TypeVar("T")


def handle_olo_response(
    response: GenericHubResponse, response_type: Type[T] | None = None
) -> Union[T, str]:
    """
    Handle Olo API response and convert to appropriate type.

    Args:
        response: The GenericHubResponse object
        response_type: Optional type to validate and convert the response to

    Returns:
        The converted response object or raw response string if no type specified

    Raises:
        ValueError: If the response status is not 200 or validation fails
    """
    if response.status != 200:
        error_msg = (
            f"API call failed with status {response.status}: {response.decoded_body}"
        )
        logger.error(f"[OLO] {error_msg}")
        raise ValueError(error_msg)

    if response_type:
        try:
            return response_type.model_validate_json(response.decoded_body)  # type: ignore
        except Exception as e:
            error_msg = (
                f"Failed to validate response as {response_type.__name__}: {str(e)}"
            )
            logger.error(f"[OLO] {error_msg}", exc_info=True)
            raise ValueError(error_msg)

    return response.decoded_body


def connect_olo_order_hub(
    http_method: HttpMethod,
    bearer_token: OloAccessToken,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
) -> GenericHubResponse:
    """
    Make a request to the Olo Order Hub API using the generic connect function.

    Args:
        http_method: The HTTP method to use
        bearer_token: The Olo access token
        api_function: The API endpoint to call
        query_params: Optional query parameters
        extra_headers: Optional additional headers
        payload: Optional request payload

    Returns:
        GenericHubResponse: The API response

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    # Build OLO-specific required headers
    olo_headers = _get_olo_required_headers()

    # Merge with any extra headers (extra_headers take precedence)
    if extra_headers:
        filtered_headers = {
            k: v
            for k, v in extra_headers.items()
            if k
            not in [
                "Date",
                "Content-Type",
                "Authorization",
                "User-Agent",
                "X-Forwarded-For",
                "X-Forwarded-UAH",
            ]
        }
        olo_headers.update(filtered_headers)
    return connect_order_hub(
        provider=ApiProvider.OLO,
        http_method=http_method,
        bearer_token=bearer_token,
        api_function=api_function,
        query_params=query_params,
        extra_headers=olo_headers,
        payload=payload,
    )


def _create_signature(
    client_secret: str,
    client_id: str,
    http_verb: str,
    content_type: str,
    hashed_body: str,
    path_and_query: str,
    time_stamp: str,
) -> str:
    """
    Creates HMAC-SHA256 signature for Olo signed requests.

    Args:
        client_secret: The client secret for signing
        client_id: The client ID
        http_verb: HTTP method (GET, POST, etc.)
        content_type: Content-Type header value
        hashed_body: Base64-encoded SHA256 hash of request body
        path_and_query: The path and query string
        time_stamp: RFC 2822 formatted timestamp

    Returns:
        Base64-encoded signature string
    """
    message_to_sign = f"{client_id}\n{http_verb}\n{content_type}\n{hashed_body}\n{path_and_query}\n{time_stamp}"
    hmac_sha256 = hmac.new(
        client_secret.encode("utf-8"),
        message_to_sign.encode("utf-8"),
        hashlib.sha256,
    )
    return base64.b64encode(hmac_sha256.digest()).decode("utf-8")


def _hash_request_body(body: str) -> str:
    """
    Creates SHA256 hash of request body.

    Args:
        body: The request body string

    Returns:
        Base64-encoded SHA256 hash
    """
    sha256_hasher = hashlib.sha256()
    sha256_hasher.update(body.encode("utf-8"))
    hash_bytes = sha256_hasher.digest()
    return base64.b64encode(hash_bytes).decode("utf-8")


def _generate_random_ip_10_0_0_0() -> str:
    """
    Generate a random IP address in the 10.0.0.0/8 range.
    This is used for the X-Forwarded-For header as required by OLO API.

    Returns:
        str: Random IP address like "10.123.45.67"
    """
    return (
        f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
    )


def _get_olo_required_headers() -> dict[str, str]:
    """
    Get the required headers for OLO API requests as per their security requirements.

    Returns:
        dict[str, str]: Dictionary containing the three required headers:
            - User-Agent: Identifies the application with brand name
            - X-Forwarded-For: Client IP address (random 10.x.x.x for testing) -
                               FIRST address must be the client IP for fraud prevention
            - X-Forwarded-UAH: User agent header identifier (generic value)
    """
    return {
        "User-Agent": "PalonaAI/Mooyah/1.0",
        "X-Forwarded-For": _generate_random_ip_10_0_0_0(),
        "X-Forwarded-UAH": "PalonaAIVoice",
    }


def connect_olo_order_hub_signed(
    http_method: HttpMethod,
    signed_token: OloSignedToken,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
    base_url: str = "ordering.api.olosandbox.com",
) -> GenericHubResponse:
    """
    Make a request to the Olo Order Hub API using signed signature authentication.

    Args:
        http_method: The HTTP method to use
        signed_token: The Olo signed token with client credentials
        api_function: The API endpoint to call
        query_params: Optional query parameters
        extra_headers: Optional additional headers. Note: Date, Content-Type, and Authorization headers will be ignored if provided in extra_headers.
        payload: Optional request payload
        base_url: The base URL for the Olo API

    Returns:
        GenericHubResponse: The API response

    Raises:
        ValueError: If the HTTP method is invalid or the request fails
    """
    logger.debug(
        f"[OLO] OloUtils.connect_olo_order_hub_signed Calling OLO Signed API: {http_method} {api_function} | "
        f"Query Params: {query_params} | "
        f"Extra Headers: {extra_headers} | "
        f"Payload: {payload}"
    )

    # Build the full path
    path_and_query = api_function
    if query_params:
        path_and_query += "?" + urllib.parse.urlencode(query_params)

    # Prepare request body
    request_body = ""
    if payload is not None:
        if isinstance(payload, dict):
            # Preserve the same JSON canonical form used for hashing and body.
            request_body = json.dumps(payload, separators=(",", ":"))
        else:
            request_body = str(payload)

    # Content type should be blank for verbs without a body (e.g., GET).
    has_body = bool(request_body)
    content_type = "application/json" if has_body else ""

    # Generate timestamp
    time_stamp = formatdate(timeval=None, localtime=False, usegmt=True)

    # Hash the request body
    hashed_body = _hash_request_body(request_body)

    # Convert http_method to string
    if isinstance(http_method, HttpMethod):
        method_str = http_method.value
    else:
        method_str = str(http_method).upper()

    # Create signature
    signed_message = _create_signature(
        client_secret=signed_token.client_secret,
        client_id=signed_token.client_id,
        http_verb=method_str,
        content_type=content_type,
        hashed_body=hashed_body,
        path_and_query=path_and_query,
        time_stamp=time_stamp,
    )

    # Build headers starting with OLO required headers
    headers = _get_olo_required_headers()

    # Add authentication and content headers
    headers.update(
        {
            "Authorization": f"{signed_token.token_type} {signed_token.client_id}:{signed_message}",
            "Date": time_stamp,
        }
    )
    if has_body:
        headers["Content-Type"] = content_type

    # Add extra headers, but exclude signature-critical headers to prevent overrides
    if extra_headers:
        filtered_headers = {
            k: v
            for k, v in extra_headers.items()
            if k
            not in [
                "Date",
                "Content-Type",
                "Authorization",
                "User-Agent",
                "X-Forwarded-For",
                "X-Forwarded-UAH",
            ]
        }
        headers.update(filtered_headers)

    try:
        conn = http.client.HTTPSConnection(base_url, timeout=30)

        # Make the request
        conn.request(method_str, path_and_query, request_body, headers)
        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        # Check for success
        if response.status != 200:
            raise Exception(
                f"Error: {response.status} - {response.reason} - {response_data}"
            )

        hub_response = GenericHubResponse(
            status=response.status,
            reason=response.reason,
            decoded_body=response_data,
        )

        logger.debug(
            f"[OLO] OloUtils.connect_olo_order_hub_signed Response: {hub_response}"
        )
        return hub_response

    except Exception as e:
        raise Exception(
            f"[OLO] OloUtils.connect_olo_order_hub_signed Error while calling {method_str} {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
