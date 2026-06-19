from __future__ import annotations

import sys
import types
from importlib import util
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from services.folk_notion_sync._settings import FolkNotionSyncSettings
from services.folk_notion_sync._webhook import FolkWebhookEvent

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ROUTE_PATH = _REPO_ROOT / "api" / "routes" / "integrations" / "folk" / "__init__.py"


@pytest.mark.asyncio
async def test_folk_webhook_returns_disabled_without_secret_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route_module(monkeypatch)

    def fail_secret_lookup(_key: str) -> str:
        raise AssertionError("secret lookup should not run when disabled")

    monkeypatch.setattr(
        route,
        "get_folk_notion_sync_settings",
        lambda: FolkNotionSyncSettings(enabled=False),
    )
    monkeypatch.setattr(route, "get_server_secret_with_fallback", fail_secret_lookup)

    result = await route.folk_webhook(_request(b"{}"), BackgroundTasks())

    assert result == {"status": "disabled"}


@pytest.mark.asyncio
async def test_folk_webhook_returns_500_when_secret_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route_module(monkeypatch)
    monkeypatch.setattr(
        route,
        "get_folk_notion_sync_settings",
        lambda: _enabled_settings(),
    )
    monkeypatch.setattr(
        route,
        "get_server_secret_with_fallback",
        _raise_missing_secret,
    )

    with pytest.raises(HTTPException) as exc_info:
        await route.folk_webhook(_request(b"{}"), BackgroundTasks())

    assert exc_info.value.status_code == 500
    assert exc_info.value.headers == {"Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_folk_webhook_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route_module(monkeypatch)
    monkeypatch.setattr(
        route,
        "get_folk_notion_sync_settings",
        lambda: _enabled_settings(),
    )
    monkeypatch.setattr(
        route,
        "get_server_secret_with_fallback",
        lambda _key: "secret",
    )
    monkeypatch.setattr(
        route,
        "verify_folk_webhook_signature",
        lambda _body, _headers, _secret: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await route.folk_webhook(_request(b"{}"), BackgroundTasks())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid Folk webhook signature"


@pytest.mark.asyncio
async def test_folk_webhook_rejects_invalid_payload_after_valid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route_module(monkeypatch)
    monkeypatch.setattr(
        route,
        "get_folk_notion_sync_settings",
        lambda: _enabled_settings(),
    )
    monkeypatch.setattr(
        route,
        "get_server_secret_with_fallback",
        lambda _key: "secret",
    )
    monkeypatch.setattr(
        route,
        "verify_folk_webhook_signature",
        lambda _body, _headers, _secret: True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await route.folk_webhook(_request(b"{"), BackgroundTasks())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid Folk webhook payload"


@pytest.mark.asyncio
async def test_folk_webhook_accepts_and_schedules_background_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _route_module(monkeypatch)
    settings = _enabled_settings()
    event = FolkWebhookEvent(
        id="evt_123",
        type="object.updated",
        created_at="2026-06-18T12:00:00.000Z",
        resource_id="obj_123",
        resource_url="https://api.folk.app/v1/groups/grp_test/Deals/obj_123",
        payload={},
    )
    background_tasks = BackgroundTasks()

    monkeypatch.setattr(route, "get_folk_notion_sync_settings", lambda: settings)
    monkeypatch.setattr(
        route,
        "get_server_secret_with_fallback",
        lambda _key: "secret",
    )
    monkeypatch.setattr(
        route,
        "verify_folk_webhook_signature",
        lambda _body, _headers, _secret: True,
    )
    monkeypatch.setattr(
        route,
        "parse_folk_webhook_event",
        lambda _body: event,
    )

    result = await route.folk_webhook(_request(b"{}"), background_tasks)

    assert result == {"status": "accepted"}
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.args == (event,)
    assert task.kwargs == {"settings": settings}


def _enabled_settings() -> FolkNotionSyncSettings:
    return FolkNotionSyncSettings(enabled=True, notion_data_source_id="ds_123")


def _route_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake_secret: Any = types.ModuleType("utils.secret")
    fake_secret.get_server_secret_with_fallback = lambda _key: "secret"
    monkeypatch.setitem(sys.modules, "utils.secret", fake_secret)
    module_name = "folk_route_under_test"
    spec = util.spec_from_file_location(module_name, _ROUTE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Folk route module")
    module = util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _raise_missing_secret(_key: str) -> str:
    raise ValueError("missing")


def _request(body: bytes, headers: dict[str, str] | None = None) -> Request:
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/integrations/folk/webhook",
            "headers": raw_headers,
        },
        receive,
    )
