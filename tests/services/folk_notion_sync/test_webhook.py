from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from services.folk_notion_sync._webhook import (
    parse_folk_webhook_event,
    verify_folk_webhook_signature,
)


def test_verify_folk_webhook_signature_accepts_standard_webhooks_signature() -> None:
    body = json.dumps(
        {
            "id": "evt_123",
            "type": "object.updated",
            "createdAt": "2026-06-18T12:00:00.000Z",
            "data": {
                "id": "obj_123",
                "url": "https://api.folk.app/v1/groups/grp_123/Deals/obj_123",
            },
        }
    ).encode("utf-8")
    secret_bytes = b"test-secret"
    signing_secret = f"whsec_{base64.b64encode(secret_bytes).decode('ascii')}"
    timestamp = "1781800000"
    signed_content = b".".join([b"evt_123", timestamp.encode("utf-8"), body])
    signature = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode("ascii")

    assert verify_folk_webhook_signature(
        body,
        {
            "webhook-id": "evt_123",
            "webhook-timestamp": timestamp,
            "webhook-signature": f"v1,{signature}",
        },
        signing_secret,
        now_seconds=1781800000,
    )


def test_verify_folk_webhook_signature_rejects_wrong_signature() -> None:
    assert not verify_folk_webhook_signature(
        b"{}",
        {
            "webhook-id": "evt_123",
            "webhook-timestamp": "1781800000",
            "webhook-signature": "v1,wrong",
        },
        f"whsec_{base64.b64encode(b'test-secret').decode('ascii')}",
        now_seconds=1781800000,
    )


@pytest.mark.parametrize(
    ("headers", "now_seconds"),
    [
        ({}, 1781800000),
        (
            {
                "webhook-id": "evt_123",
                "webhook-timestamp": "not-an-int",
                "webhook-signature": "v1,wrong",
            },
            1781800000,
        ),
        (
            {
                "webhook-id": "evt_123",
                "webhook-timestamp": "1781790000",
                "webhook-signature": "v1,wrong",
            },
            1781800000,
        ),
    ],
)
def test_verify_folk_webhook_signature_rejects_invalid_headers(
    headers: dict[str, str],
    now_seconds: int,
) -> None:
    assert not verify_folk_webhook_signature(
        b"{}",
        headers,
        f"whsec_{base64.b64encode(b'test-secret').decode('ascii')}",
        now_seconds=now_seconds,
    )


def test_parse_folk_webhook_event_extracts_required_fields() -> None:
    event = parse_folk_webhook_event(
        json.dumps(
            {
                "id": "evt_123",
                "type": "object.created",
                "createdAt": "2026-06-18T12:00:00.000Z",
                "data": {
                    "id": "obj_123",
                    "url": "https://api.folk.app/v1/groups/grp_123/Deals/obj_123",
                },
            }
        ).encode("utf-8")
    )

    assert event.id == "evt_123"
    assert event.type == "object.created"
    assert event.resource_id == "obj_123"
    assert event.resource_url.endswith("/obj_123")


@pytest.mark.parametrize("body", [b"\xff", b"{"])
def test_parse_folk_webhook_event_rejects_malformed_json(body: bytes) -> None:
    with pytest.raises(ValueError, match="Invalid Folk webhook payload"):
        parse_folk_webhook_event(body)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "evt_123", "type": "object.created", "createdAt": "now", "data": []},
    ],
)
def test_parse_folk_webhook_event_requires_data_object(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="missing data"):
        parse_folk_webhook_event(json.dumps(payload).encode("utf-8"))


def test_parse_folk_webhook_event_requires_resource_fields() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        parse_folk_webhook_event(
            json.dumps(
                {
                    "id": "evt_123",
                    "type": "object.created",
                    "createdAt": "2026-06-18T12:00:00.000Z",
                    "data": {"id": "obj_123"},
                }
            ).encode("utf-8")
        )
