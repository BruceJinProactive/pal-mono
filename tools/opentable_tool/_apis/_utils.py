import http.client
import json
from typing import Optional

from tools.opentable_tool.classes import (
    HttpMethod,
    OpenTableAccessToken,
    OpenTableResponse,
)
from utils.log import logger

DEFAULT_TIMEOUT = 30


def connect_opentable_api(
    http_method: HttpMethod,
    bearer_token: OpenTableAccessToken,
    api_function: str,
    payload: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> OpenTableResponse:
    """Minimal wrapper around OpenTable's internal JSON API."""

    headers = {
        "Content-Type": "application/json",
        "x-csrf-token": bearer_token.access_token,
    }

    body = None
    if payload is not None:
        try:
            body = json.dumps(payload).encode("utf-8")
        except TypeError as exc:
            logger.error("[OpenTable API] Failed to encode payload: %s", exc)
            return OpenTableResponse(
                status=500,
                reason="Payload serialization failed",
                decoded_body={"error": str(exc)},
            )

    conn = http.client.HTTPSConnection("www.opentable.com", timeout=timeout)
    try:
        conn.request(http_method.value, api_function, body, headers)
        res = conn.getresponse()
        raw_body = res.read().decode("utf-8")

        decoded: object
        try:
            decoded = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            decoded = {"raw_content": raw_body}

        return OpenTableResponse(
            status=res.status, reason=res.reason, decoded_body=decoded
        )
    except http.client.HTTPException as exc:
        logger.error("[OpenTable API] HTTP error: %s", exc)
        return OpenTableResponse(
            status=500,
            reason="HTTP Error",
            decoded_body={"error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001 - surface unexpected issues
        logger.error("[OpenTable API] Unexpected error", exc_info=True)
        return OpenTableResponse(
            status=500,
            reason="Unexpected error",
            decoded_body={"error": str(exc)},
        )
    finally:
        conn.close()
