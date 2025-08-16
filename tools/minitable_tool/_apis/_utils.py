import base64
import json
from typing import Dict, Optional

import requests

from utils.log import logger
from utils.secret import get_client_secret_with_fallback

DEFAULT_TIMEOUT = 10
MINITABLE_HOST = "ai.minitable.link"


class MiniTableResponse:
    """Class to handle MiniTable API response data"""

    def __init__(self, status: int, reason: str, decoded_body: Dict):
        self.status = status
        self.reason = reason
        self.decoded_body = decoded_body


def connect_minitable_api(
    api_function: str,
    payload: Optional[dict] = None,
) -> MiniTableResponse:
    """
    Makes a request to the MiniTable API.

    Args:
        api_function: API endpoint to call
        payload: JSON payload to include in the request

    Returns:
        MiniTableResponse object containing the response data
    """
    # Construct full URL
    base_url = f"https://{MINITABLE_HOST}/{api_function}"

    logger.debug(f"[MiniTable API] Making POST request to {base_url}")

    try:
        username = get_client_secret_with_fallback("MINITABLE_USERNAME")
        password = get_client_secret_with_fallback("MINITABLE_PASSWORD")
    except Exception as e:
        logger.error(f"[MiniTable API] Failed to retrieve credentials: {str(e)}")
        return MiniTableResponse(
            status=500,
            reason=f"Failed to retrieve credentials: {str(e)}",
            decoded_body={},
        )

    # Create Basic Auth header
    credentials = f"{username}:{password}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}",
    }

    try:
        response = requests.post(
            url=base_url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT
        )

        logger.debug(
            f"[MiniTable API] Response received: {response.status_code} {response.reason}"
        )

        decoded_body = {}
        try:
            decoded_body = response.json()
            logger.debug("[MiniTable API] Successfully parsed JSON response")
        except json.JSONDecodeError as e:
            logger.error(f"[MiniTable API] Failed to decode JSON response: {e}")
            decoded_body = {"raw_content": response.text, "parse_error": str(e)}

        return MiniTableResponse(
            status=response.status_code,
            reason=response.reason,
            decoded_body=decoded_body,
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"[MiniTable API] Request error: {str(e)}")
        return MiniTableResponse(
            status=500,
            reason=f"Request error: {str(e)}",
            decoded_body={"error": str(e)},
        )
    except Exception as e:
        logger.error(f"[MiniTable API] Unexpected error: {str(e)}", exc_info=True)
        return MiniTableResponse(
            status=500,
            reason=f"Unexpected error: {str(e)}",
            decoded_body={"error": str(e)},
        )
