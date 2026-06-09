from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_checkout_session_uses_uuid_lookup(monkeypatch):
    from api.routes.integrations.toast import _implementation

    expected_token = uuid.uuid4()
    payload = {"orderExternalId": "PALONA:test", "expiresAt": 9999999999}
    captured: dict = {}

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_get_checkout_session_payload_async(session, token):
        captured["session"] = session
        captured["token"] = token
        return payload

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation,
        "get_checkout_session_payload_async",
        _fake_get_checkout_session_payload_async,
    )

    response = await _implementation.get_checkout_session(str(expected_token))

    assert response.status_code == 200
    assert captured["token"] == expected_token
    assert response.body


@pytest.mark.asyncio
async def test_get_checkout_session_returns_404_for_missing_uuid(monkeypatch):
    from api.routes.integrations.toast import _implementation

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_get_checkout_session_payload_async(session, token):
        raise _implementation.ToastCheckoutSessionNotFoundError

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation,
        "get_checkout_session_payload_async",
        _fake_get_checkout_session_payload_async,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _implementation.get_checkout_session(str(uuid.uuid4()))

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_checkout_session_returns_400_for_invalid_uuid():
    from api.routes.integrations.toast import _implementation

    with pytest.raises(HTTPException) as exc_info:
        await _implementation.get_checkout_session("not-a-uuid")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_checkout_session_returns_400_for_expired_session(monkeypatch):
    from api.routes.integrations.toast import _implementation

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def _fake_get_checkout_session_payload_async(session, token):
        raise _implementation.ToastCheckoutSessionExpiredError

    monkeypatch.setattr(_implementation, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        _implementation,
        "get_checkout_session_payload_async",
        _fake_get_checkout_session_payload_async,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _implementation.get_checkout_session(str(uuid.uuid4()))

    assert exc_info.value.status_code == 400
