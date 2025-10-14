"""Lightweight Resy API client for availability search and booking."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional

from tools.resy_tool_with_reservation._apikey import get_resy_api_key
from utils.log import logger

RESY_FIND_API_URL = "https://api.resy.com/4/find"
AUTH_REFRESH_URL = "https://auth.resy.com/1/auth/refresh"
AUTH_VENUE_URL = "https://auth.resy.com/1/auth/venue"
RESY_CONTROL_BASE_URL = "https://control.resy.com/3"
USER_AGENT = "pal-mono/1.0"
CONTROL_ORIGIN = "https://os.resy.com"
STAFF_ID = "1214756"


class ResyAPIError(RuntimeError):
    """Raised when the Resy API responds with an unexpected error."""

    def __init__(
        self,
        *,
        endpoint: str,
        status: int,
        reason: str,
        body: Optional[str] = None,
    ) -> None:
        message = f"Resy API error ({endpoint}): HTTP {status} {reason}"
        if body:
            message = f"{message} - {body}"
        super().__init__(message)
        self.endpoint = endpoint
        self.status = status
        self.reason = reason
        self.body = body


def find_resy_availability(
    *,
    venue_id: int,
    city: str,
    venue_name: str,
    day: str,
    party_size: int,
    latitude: float = 0.0,
    longitude: float = 0.0,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Call the public Resy /4/find endpoint and return the parsed JSON body."""

    api_key = get_resy_api_key(
        city=city, venue_name=venue_name, timeout=timeout, user_agent=USER_AGENT
    )

    payload = {
        "lat": latitude,
        "long": longitude,
        "day": day,
        "party_size": party_size,
        "venue_id": venue_id,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f'ResyAPI api_key="{api_key}"',
        "User-Agent": USER_AGENT,
    }

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        RESY_FIND_API_URL, data=data, headers=headers, method="POST"
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    return json.loads(body or "{}")


def refresh_universal_token(
    *, api_key: str, universal_token: str, timeout: int = 30
) -> Dict[str, Any]:
    """Refresh the universal auth token used for subsequent venue authentication."""

    headers = _build_auth_headers(api_key=api_key, token=universal_token)
    response = _request_json(
        AUTH_REFRESH_URL, headers=headers, data=b"", timeout=timeout
    )
    return response


def authorize_venue(
    *,
    api_key: str,
    universal_token: str,
    venue_id: int,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Request a venue-scoped auth token using the refreshed universal auth token."""

    headers = _build_auth_headers(api_key=api_key, token=universal_token)
    headers["Content-Type"] = "application/json"
    payload = json.dumps({"venue_id": venue_id}).encode("utf-8")

    response = _request_json(
        AUTH_VENUE_URL, headers=headers, data=payload, timeout=timeout
    )
    return response


def create_guest(
    *,
    api_key: str,
    auth_token: str,
    first_name: str,
    last_name: str,
    phone_number: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Create or update a guest record in the venue guestbook."""

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "email": "",
        "mobile_number": phone_number,
    }

    response = _post_to_control(
        endpoint="/guestbook",
        api_key=api_key,
        auth_token=auth_token,
        payload=payload,
        timeout=timeout,
    )
    return response


def search_guest_by_phone(
    *,
    api_key: str,
    auth_token: str,
    phone_number: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Search the guestbook for an existing guest by phone number."""

    query = urllib.parse.quote(phone_number)
    url = f"https://guestbook.resy.com/1/search?query={query}"
    headers = _build_auth_headers(api_key=api_key, token=auth_token)
    response = _request_json(url, headers=headers, data=None, timeout=timeout)
    return response


def create_reservation_lock(
    *,
    api_key: str,
    auth_token: str,
    venue_id: int,
    date: str,
    time: str,
    party_size: int,
    template_id: int | str,
    config_type: str,
    service_type_id: int | str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Obtain a lock token for the requested slot prior to booking."""

    payload = {
        "date": date,
        "shift_date": date,
        "time": time,
        "service_type_id": service_type_id,
        "availability_type": 2,
        "party_size": party_size,
        "overbook": False,
        "config_type": config_type,
        "template_id": template_id,
    }

    response = _post_to_control(
        endpoint="/reservation/lock",
        api_key=api_key,
        auth_token=auth_token,
        payload=payload,
        timeout=timeout,
    )
    return response


def create_reservation(
    *,
    api_key: str,
    auth_token: str,
    venue_id: int,
    template_id: int | str,
    config_type: str,
    slot_token: str,
    lock_token: str,
    guest_user_id: int | str,
    party_size: int,
    date: str,
    time: str,
    service_type_id: int | str,
    email_confirmation: bool = False,
    email_contact_confirmation: bool = False,
    first_name: str | None = None,
    last_name: str | None = None,
    phone_number: str | None = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Submit a reservation request using the provided lock and guest identifiers."""

    payload = {
        "template_id": template_id,
        "config_type": config_type,
        "token": lock_token,
        "user_id": guest_user_id,
        "staff_id": STAFF_ID,
        "struct_tags": [],
        "email_confirmation": email_confirmation,
        "email_contact_confirmation": email_contact_confirmation,
    }

    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if phone_number:
        payload["mobile_number"] = phone_number

    response = _post_to_control(
        endpoint="/reservation",
        api_key=api_key,
        auth_token=auth_token,
        payload=payload,
        timeout=timeout,
    )
    return response


def _post_to_control(
    *,
    endpoint: str,
    api_key: str,
    auth_token: str,
    payload: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    url = f"{RESY_CONTROL_BASE_URL}{endpoint}"
    headers = _build_control_headers(api_key=api_key, auth_token=auth_token)
    data, content_type = _encode_multipart_form_data(payload)
    headers["Content-Type"] = content_type

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failures
        error_body = _read_error_body(exc)
        logger.error(
            "[Resy API] HTTP error %s",
            endpoint,
            extra={"status": exc.code, "reason": exc.reason, "body": error_body},
        )
        raise ResyAPIError(
            endpoint=endpoint, status=exc.code, reason=exc.reason, body=error_body
        ) from exc

    except urllib.error.URLError as exc:  # pragma: no cover - network failures
        logger.error("[Resy API] Network error %s", endpoint, exc_info=True)
        raise RuntimeError(f"Unable to reach Resy endpoint {endpoint}: {exc}") from exc

    return json.loads(body or "{}")


def _build_control_headers(*, api_key: str, auth_token: str) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f'ResyAPI api_key="{api_key}"',
        "User-Agent": USER_AGENT,
        "X-Resy-Universal-Auth": auth_token,
        "X-Origin": CONTROL_ORIGIN,
        "Origin": CONTROL_ORIGIN,
        "Referer": f"{CONTROL_ORIGIN}/",
    }


def _build_auth_headers(*, api_key: str, token: str) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f'ResyAPI api_key="{api_key}"',
        "User-Agent": USER_AGENT,
        "X-Origin": CONTROL_ORIGIN,
        "Origin": CONTROL_ORIGIN,
        "Referer": f"{CONTROL_ORIGIN}/",
        "X-Resy-Universal-Auth": token,
    }


def _encode_multipart_form_data(data: Dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"----PalBoundary{uuid.uuid4().hex}"
    lines: list[str] = []

    for key, value in data.items():
        serialized = _serialize_form_value(value)
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{key}"')
        lines.append("")
        lines.append(serialized)

    lines.append(f"--{boundary}--")
    lines.append("")

    body = "\r\n".join(lines).encode("utf-8")
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _serialize_form_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def _read_error_body(exc: urllib.error.HTTPError) -> Optional[str]:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return None


def _request_json(
    url: str,
    *,
    headers: Dict[str, str],
    data: Optional[bytes],
    timeout: int,
    method: Optional[str] = None,
) -> Dict[str, Any]:
    actual_method = method or ("POST" if data is not None else "GET")
    request = urllib.request.Request(
        url, data=data, headers=headers, method=actual_method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failures
        logger.error(
            "[Resy API] HTTP error %s",
            url,
            extra={"status": exc.code, "reason": exc.reason},
        )
        raise ResyAPIError(endpoint=url, status=exc.code, reason=exc.reason) from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network failures
        logger.error("[Resy API] Network error %s", url, exc_info=True)
        raise RuntimeError(f"Unable to reach Resy endpoint {url}: {exc}") from exc

    return json.loads(body or "{}")


def _sanitize_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, val in value.items():
            lowered = key.lower()
            if lowered in {"token", "lock_token", "authorization", "auth"}:
                sanitized[key] = _mask_string(str(val))
            elif lowered in {"os_tokens"} and isinstance(val, dict):
                sanitized[key] = {k: _mask_string(str(v)) for k, v in val.items()}
            else:
                sanitized[key] = _sanitize_for_log(val)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    if isinstance(value, str):
        return _mask_string(value)
    return value


def _mask_string(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= 16:
        return cleaned
    return f"{cleaned[:8]}…{cleaned[-4:]}"
