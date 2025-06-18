import http.client
import urllib.parse

from pydantic import ValidationError

from tools.adora_tool.classes import AdoraAccessToken, AdoraHubResponse
from utils.log import logger


def parse_json(model_class, json_str: str):
    """
    Try to parse the JSON string into the model class.
    If it fails, print the error and return None.
    """

    try:
        data_model = model_class.model_validate_json(json_str)
        return data_model
    except ValidationError as e:
        logger.error(e)

    return None


def connect_adora_order_hub(
    http_method: str,
    auth_token: AdoraAccessToken,
    api_function: str,
    query_params: dict | None = None,
    extra_headers: dict | None = None,
    payload: str | None = "",
    qa_store: bool = False,
    general_api_endpoint: str | None = None,
) -> AdoraHubResponse:
    """Utility function to connect to Adora Order Hub API"""
    # Validate custom endpoint if provided
    if general_api_endpoint:
        try:
            parsed = urllib.parse.urlparse(f"https://{general_api_endpoint}")
            if not parsed.netloc or parsed.scheme != "https":
                raise ValueError("Invalid endpoint format")
        except Exception as e:
            raise ValueError(
                f"Invalid general_api_endpoint: {general_api_endpoint}"
            ) from e

    logger.debug(
        f"[AdoraTool._apis._utils.connect_adora_order_hub] Calling Adora API: {http_method} {api_function} | "
        f"Query Params: {query_params} | "
        f"Extra Headers: {extra_headers} | "
        f"Payload: {payload}"
    )

    if general_api_endpoint:
        conn = http.client.HTTPSConnection(general_api_endpoint)
    else:
        if qa_store:
            conn = http.client.HTTPSConnection("adora-qa-api-public.azurewebsites.net")
        else:
            conn = http.client.HTTPSConnection("public.api.adorapos.net")

    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_token.get_token_header_value(),
    }
    if extra_headers:
        headers.update(extra_headers)

    path_plus_params = "/api/v1/OrderHub/" + api_function

    if query_params:
        path_plus_params = path_plus_params + "?" + urllib.parse.urlencode(query_params)

    if http_method == "GET":
        conn.request("GET", path_plus_params, payload, headers)
    elif http_method == "POST":
        conn.request("POST", path_plus_params, payload, headers)
    else:
        assert False, "Invalid HTTP method for Adora Pos API"

    res = conn.getresponse()
    data = res.read()
    response_body = data.decode("utf-8")

    order_hub_response = AdoraHubResponse(
        status=res.status, reason=res.reason, decoded_body=response_body
    )

    logger.debug(
        f"[AdoraTool._apis._utils.connect_adora_order_hub] Response: {order_hub_response}"
    )

    return order_hub_response
