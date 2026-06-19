from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

_WEBHOOK_TOLERANCE_SECONDS = 300


@dataclass(frozen=True)
class FolkWebhookEvent:
    id: str
    type: str
    created_at: str
    resource_id: str
    resource_url: str
    payload: dict[str, Any]


def parse_folk_webhook_event(body: bytes) -> FolkWebhookEvent:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Folk webhook payload") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Folk webhook payload is missing data")

    event_id = payload.get("id")
    event_type = payload.get("type")
    created_at = payload.get("createdAt")
    resource_id = data.get("id")
    resource_url = data.get("url")
    if (
        not isinstance(event_id, str)
        or not isinstance(event_type, str)
        or not isinstance(created_at, str)
        or not isinstance(resource_id, str)
        or not isinstance(resource_url, str)
        or not event_id
        or not event_type
        or not created_at
        or not resource_id
        or not resource_url
    ):
        raise ValueError("Folk webhook payload is missing required fields")

    return FolkWebhookEvent(
        id=event_id,
        type=event_type,
        created_at=created_at,
        resource_id=resource_id,
        resource_url=resource_url,
        payload=payload,
    )


def verify_folk_webhook_signature(
    body: bytes,
    headers: Mapping[str, str],
    signing_secret: str,
    *,
    now_seconds: int | None = None,
) -> bool:
    webhook_id = _header_value(headers, "webhook-id")
    webhook_timestamp = _header_value(headers, "webhook-timestamp")
    webhook_signature = _header_value(headers, "webhook-signature")
    if not webhook_id or not webhook_timestamp or not webhook_signature:
        return False

    try:
        timestamp = int(webhook_timestamp)
    except ValueError:
        return False

    current_time = int(time.time()) if now_seconds is None else now_seconds
    if abs(current_time - timestamp) > _WEBHOOK_TOLERANCE_SECONDS:
        return False

    secret_bytes = _decode_standard_webhooks_secret(signing_secret)
    signed_content = b".".join(
        [
            webhook_id.encode("utf-8"),
            webhook_timestamp.encode("utf-8"),
            body,
        ]
    )
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode("ascii")

    return any(
        hmac.compare_digest(expected, candidate)
        for candidate in _signature_candidates(webhook_signature)
    )


def _header_value(headers: Mapping[str, str], key: str) -> str:
    for header_key, value in headers.items():
        if header_key.lower() == key:
            return value
    return ""


def _decode_standard_webhooks_secret(signing_secret: str) -> bytes:
    secret = signing_secret.removeprefix("whsec_")
    return base64.b64decode(secret)


def _signature_candidates(signature_header: str) -> list[str]:
    candidates: list[str] = []
    for part in signature_header.replace(" ", ",").split(","):
        cleaned = part.strip()
        if cleaned and cleaned != "v1":
            candidates.append(cleaned)
    return candidates
