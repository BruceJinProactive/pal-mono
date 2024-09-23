import http
import urllib
from typing import Optional

from jsonschema import ValidationError

from ai.tools.ordering_tools.integrations.adora.classes import (
    AccessToken,
    AdoraHubResponse,
)
from utils.log import logger


def parse_json(model_class, json_str: str):
    """Try to parse the JSON string into the model class. If it fails, print the error and return None."""

    try:
        data_model = model_class.model_validate_json(json_str)
        return data_model
    except ValidationError as e:
        logger.error(e)

    return None


def connect_adora_order_hub(
    http_method: str,
    auth_token: AccessToken,
    api_function: str,
    query_params: Optional[dict] = None,
    extra_headers: Optional[dict] = None,
    payload: Optional[str] = "",
) -> AdoraHubResponse:
    """utility function to connect to Adora Order Hub API"""

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
    return order_hub_response
