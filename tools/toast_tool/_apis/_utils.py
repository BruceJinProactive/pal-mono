import http.client
import json
import urllib.parse

from tools.toast_tool.classes import HttpMethod, ToastAccessToken, ToastHubResponse
from utils.log import logger

#################### CONSTANTS ####################
BASE_URL = "toast-api-server"

API_TIMEOUT = 30  # seconds
####################################################


def connect_toast_order_hub(
    http_method: HttpMethod,
    bearer_token: ToastAccessToken,
    api_function: str,
    store_id: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: dict | str | None = None,
    logging_enabled: bool = True,
) -> ToastHubResponse:

    if logging_enabled:
        logger.info(f"Calling Toast API: {http_method} {api_function}")
        logger.info(f"Query Params: {query_params}")
        logger.info(f"Extra Headers: {extra_headers}")
        logger.info(f"Payload: {payload}")

    # Set up headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": bearer_token.get_token_header_value(),
        "Toast-Restaurant-External-ID": store_id,
    }

    # Add any extra headers
    if extra_headers:
        headers.update(extra_headers)

    # Prepare payload
    request_body = None
    if payload is not None:
        if isinstance(payload, dict):
            request_body = json.dumps(payload)
        else:
            request_body = payload

    # Construct the full URL with query parameters
    if query_params:
        api_function += "?" + urllib.parse.urlencode(query_params)

    try:
        conn = http.client.HTTPSConnection(BASE_URL, timeout=API_TIMEOUT)
        # We focus on GET and POST methods for now
        # You can add more methods as needed
        if http_method == HttpMethod.GET:
            conn.request(http_method, api_function, headers=headers)

        elif http_method == HttpMethod.POST:
            conn.request(http_method, api_function, request_body, headers)

        else:
            raise ValueError(
                f"[ToastTool._apis._utils.connect_toast_order_hub] Invalid HTTP method: {http_method}"
            )
        response = conn.getresponse()
        response_data = response.read().decode("utf-8")

        # If response status is not 200, raise an exception
        if response.status != 200:
            raise Exception(f"Error: {response.status} - {response.reason}")

        toast_response = ToastHubResponse(
            status=response.status,
            reason=response.reason,
            decoded_body=response_data,
        )
        if logging_enabled:
            logger.info(
                f"[ToastTool._apis._utils.connect_toast_order_hub] ToastResponse: {toast_response}"
            )
        return toast_response

    except Exception as e:
        raise Exception(
            f"[ToastTool._apis._utils.connect_toast_order_hub] Error while calling {http_method} {api_function}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
