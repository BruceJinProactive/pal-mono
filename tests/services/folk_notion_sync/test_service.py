from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import httpx
import pytest

from services.folk_notion_sync._mapping import CompanyProjection, DealProjection
from services.folk_notion_sync._service import process_folk_event
from services.folk_notion_sync._settings import FolkNotionSyncSettings
from services.folk_notion_sync._webhook import FolkWebhookEvent


class _FakeFolkClient:
    def __init__(self, deal: dict[str, Any], company: dict[str, Any]) -> None:
        self.deal = deal
        self.company = company

    async def get_resource_url(self, resource_url: str) -> dict[str, Any]:
        return {"data": self.deal}

    async def get_company(self, company_id: str) -> dict[str, Any]:
        return self.company

    async def list_deals(self) -> list[dict[str, Any]]:
        return [self.deal]


class _FakeNotionClient:
    def __init__(self, page: dict[str, Any] | None) -> None:
        self.page = page
        self.created: list[dict[str, Any]] = []
        self.created_children: list[list[dict[str, Any]] | None] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    async def find_page(self, company: Any) -> dict[str, Any] | None:
        return self.page

    async def create_page(
        self,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.created.append(properties)
        self.created_children.append(children)
        return {"id": "page_123"}

    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        self.updated.append((page_id, properties))
        return {"id": page_id}


@pytest.mark.asyncio
async def test_process_folk_event_creates_page_when_missing() -> None:
    deal = _deal()
    notion = _FakeNotionClient(page=None)

    await process_folk_event(
        _event("object.created"),
        settings=_settings(),
        folk_client=_FakeFolkClient(deal, _company()),
        notion_client=notion,
    )

    assert len(notion.created) == 1
    assert notion.created[0]["Name"]["title"][0]["text"]["content"] == "Acme"
    children = notion.created_children[0]
    assert children is not None
    assert children[0]["heading_2"]["rich_text"][0]["text"]["content"] == "Folk sync"
    assert notion.updated == []


@pytest.mark.asyncio
async def test_process_folk_event_updates_existing_page() -> None:
    deal = _deal()
    notion = _FakeNotionClient(page={"id": "page_existing"})

    await process_folk_event(
        _event("object.updated"),
        settings=_settings(),
        folk_client=_FakeFolkClient(deal, _company()),
        notion_client=notion,
    )

    assert notion.created == []
    assert len(notion.updated) == 1
    assert notion.updated[0][0] == "page_existing"
    assert "Name" not in notion.updated[0][1]


@pytest.mark.asyncio
async def test_process_folk_event_ignores_delete() -> None:
    notion = _FakeNotionClient(page=None)

    await process_folk_event(
        _event("object.deleted"),
        settings=_settings(),
        folk_client=_FakeFolkClient(_deal(), _company()),
        notion_client=notion,
    )

    assert notion.created == []
    assert notion.updated == []


@pytest.mark.asyncio
async def test_process_folk_event_ignores_disabled_and_unsupported_events() -> None:
    notion = _FakeNotionClient(page=None)

    await process_folk_event(
        _event("object.updated"),
        settings=_settings(enabled=False),
        folk_client=_FakeFolkClient(_deal(), _company()),
        notion_client=notion,
    )
    await process_folk_event(
        _event("object.merged"),
        settings=_settings(),
        folk_client=_FakeFolkClient(_deal(), _company()),
        notion_client=notion,
    )

    assert notion.created == []
    assert notion.updated == []


@pytest.mark.asyncio
async def test_process_folk_event_alerts_when_deal_payload_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    async def fake_send_sync_failure_alert(
        settings: FolkNotionSyncSettings,
        *,
        title: str,
        detail: str,
        event_id: str,
        event_type: str,
    ) -> None:
        _ = settings
        calls.append(
            {
                "title": title,
                "detail": detail,
                "event_id": event_id,
                "event_type": event_type,
            }
        )

    fake_alerts = types.SimpleNamespace(
        send_sync_failure_alert=fake_send_sync_failure_alert
    )
    monkeypatch.setitem(sys.modules, "services.folk_notion_sync._alerts", fake_alerts)

    await process_folk_event(
        _event("object.updated"),
        settings=_settings(),
        folk_client=_FakeFolkClient({}, _company()),
        notion_client=_FakeNotionClient(page=None),
    )

    assert calls == [
        {
            "title": "object.updated for obj_123",
            "detail": "Folk deal payload was empty for obj_123",
            "event_id": "evt_123",
            "event_type": "object.updated",
        }
    ]


@pytest.mark.asyncio
async def test_folk_client_does_not_retry_non_retryable_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, json={"error": "unauthorized"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(max_retries=3),
            api_key="folk-test-key",
            http_client=client,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await folk_client.get_resource_url("https://api.folk.app/v1/example")

    assert len(requests) == 1


@pytest.mark.asyncio
async def test_folk_client_lists_paginated_deals_and_filters_non_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [{"id": "obj_1"}, "ignore-me"],
                        "pagination": {
                            "nextLink": "https://api.folk.app/v1/groups/grp_test/Deals?page=2"
                        },
                    }
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={"data": {"items": [{"id": "obj_2"}], "pagination": {}}},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(),
            api_key="folk-test-key",
            http_client=client,
        )

        deals = await folk_client.list_deals()

    assert deals == [{"id": "obj_1"}, {"id": "obj_2"}]
    assert requests[0].headers["Authorization"] == "Bearer folk-test-key"
    assert [request.url.params.get("limit") for request in requests] == ["100", None]


@pytest.mark.asyncio
async def test_folk_client_updates_company_and_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"id": "updated"}}, request=request)

    payload = {"customFieldValues": {"grp_test": {"Account Name": "acme"}}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(),
            api_key="folk-test-key",
            http_client=client,
        )

        company = await folk_client.update_company("com_123", payload)
        contact = await folk_client.update_contact("per_123", payload)

    assert company == {"id": "updated"}
    assert contact == {"id": "updated"}
    assert [request.method for request in requests] == ["PATCH", "PATCH"]
    assert requests[0].url.path == "/v1/companies/com_123"
    assert requests[1].url.path == "/v1/contacts/per_123"
    assert json_body(requests[0]) == payload
    assert json_body(requests[1]) == payload


@pytest.mark.asyncio
async def test_folk_client_creates_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={"data": {"id": "folk-company-created"}},
            request=request,
        )

    payload = {"name": "Acme Inc."}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(),
            api_key="folk-test-key",
            http_client=client,
        )

        company = await folk_client.create_company(payload)

    assert company == {"id": "folk-company-created"}
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/companies"
    assert json_body(requests[0]) == payload


@pytest.mark.asyncio
async def test_folk_client_lists_paginated_companies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [{"id": "com_1", "name": "Acme Inc."}],
                        "pagination": {
                            "nextLink": "https://api.folk.app/v1/companies?page=2"
                        },
                    }
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [{"id": "com_2", "name": "Beta Inc."}],
                    "pagination": {},
                }
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(),
            api_key="folk-test-key",
            http_client=client,
        )

        companies = await folk_client.list_companies()

    assert companies == [
        {"id": "com_1", "name": "Acme Inc."},
        {"id": "com_2", "name": "Beta Inc."},
    ]
    assert [request.method for request in requests] == ["GET", "GET"]
    assert requests[0].url.path == "/v1/companies"
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.path == "/v1/companies"


@pytest.mark.asyncio
async def test_folk_client_retries_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.25"},
                json={"error": "rate_limited"},
                request=request,
            )
        return httpx.Response(200, json={"data": {"id": "com_123"}}, request=request)

    monkeypatch.setattr(folk_module.asyncio, "sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(max_retries=1),
            api_key="folk-test-key",
            http_client=client,
        )

        company = await folk_client.get_company("com_123")

    assert company == {"id": "com_123"}
    assert len(requests) == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_folk_client_retries_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("temporary network error", request=request)
        return httpx.Response(200, json={"data": {"id": "com_123"}}, request=request)

    monkeypatch.setattr(folk_module.asyncio, "sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(max_retries=1),
            api_key="folk-test-key",
            http_client=client,
        )

        company = await folk_client.get_company("com_123")

    assert company == {"id": "com_123"}
    assert len(requests) == 2
    assert sleeps == [1]


@pytest.mark.asyncio
async def test_folk_client_raises_on_malformed_list_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(),
            api_key="folk-test-key",
            http_client=client,
        )

        with pytest.raises(ValueError, match="missing object `data`"):
            await folk_client.list_deals()


@pytest.mark.asyncio
async def test_folk_client_rejects_resource_urls_outside_configured_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._folk", raising=False)
    folk_module: Any = importlib.import_module("services.folk_notion_sync._folk")
    folk_client_class: Any = folk_module.FolkClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {}}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        folk_client = folk_client_class(
            _settings(),
            api_key="folk-test-key",
            http_client=client,
        )

        with pytest.raises(ValueError, match="Unexpected Folk resource URL origin"):
            await folk_client.get_resource_url("https://evil.example/v1/example")

    assert requests == []


@pytest.mark.asyncio
async def test_notion_client_queries_pages_and_writes_page_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._notion", raising=False)
    notion_module: Any = importlib.import_module("services.folk_notion_sync._notion")
    notion_client_class: Any = notion_module.NotionDataSourceClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/query"):
            payload = json_body(request)
            if "start_cursor" not in payload:
                return httpx.Response(
                    200,
                    json={
                        "results": [{"id": "page_1"}, "ignore-me"],
                        "has_more": True,
                        "next_cursor": "cursor_2",
                    },
                    request=request,
                )
            return httpx.Response(
                200,
                json={"results": [{"id": "page_2"}], "has_more": False},
                request=request,
            )
        return httpx.Response(200, json={"id": "written_page"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notion_client = notion_client_class(
            _settings(),
            api_key="notion-test-key",
            http_client=client,
        )

        pages = await notion_client.query_pages()
        created = await notion_client.create_page({"Name": {}}, children=[{"x": 1}])
        updated = await notion_client.update_page("page_1", {"Name": {}})

    assert pages == [{"id": "page_1"}, {"id": "page_2"}]
    assert created == {"id": "written_page"}
    assert updated == {"id": "written_page"}
    assert requests[0].headers["Authorization"] == "Bearer notion-test-key"
    assert json_body(requests[1])["start_cursor"] == "cursor_2"
    assert json_body(requests[2])["children"] == [{"x": 1}]
    assert requests[3].method == "PATCH"


@pytest.mark.asyncio
async def test_notion_client_find_page_matches_ids_and_normalized_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._notion", raising=False)
    notion_module: Any = importlib.import_module("services.folk_notion_sync._notion")
    notion_client_class: Any = notion_module.NotionDataSourceClient

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        _notion_page(
                            "page_company",
                            company_ids="com_123",
                            deal_ids="obj_999",
                        ),
                        _notion_page("page_deal", deal_ids="obj_123"),
                        _notion_page("page_name", name="Acme Restaurant LLC"),
                    ],
                    "has_more": False,
                },
                request=request,
            )
        )
    ) as client:
        notion_client = notion_client_class(
            _settings(),
            api_key="notion-test-key",
            http_client=client,
        )

        by_company = await notion_client.find_page(_projection(company_id="com_123"))
        by_deal = await notion_client.find_page(_projection(company_id="com_missing"))
        by_name = await notion_client.find_page(
            _projection(company_id="com_missing", deal_id="obj_missing")
        )

    assert by_company is not None
    assert by_company["id"] == "page_company"
    assert by_deal is not None
    assert by_deal["id"] == "page_deal"
    assert by_name is not None
    assert by_name["id"] == "page_name"


@pytest.mark.asyncio
async def test_notion_client_find_page_rejects_duplicate_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._notion", raising=False)
    notion_module: Any = importlib.import_module("services.folk_notion_sync._notion")
    notion_client_class: Any = notion_module.NotionDataSourceClient

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        _notion_page("page_1", company_ids="com_123"),
                        _notion_page("page_2", company_ids="com_123"),
                    ],
                    "has_more": False,
                },
                request=request,
            )
        )
    ) as client:
        notion_client = notion_client_class(
            _settings(),
            api_key="notion-test-key",
            http_client=client,
        )

        with pytest.raises(ValueError, match="Multiple Notion pages"):
            await notion_client.find_page(_projection(company_id="com_123"))


@pytest.mark.asyncio
async def test_notion_client_does_not_retry_non_retryable_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._notion", raising=False)
    notion_module: Any = importlib.import_module("services.folk_notion_sync._notion")
    notion_client_class: Any = notion_module.NotionDataSourceClient
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": "bad request"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notion_client = notion_client_class(
            _settings(max_retries=3),
            api_key="notion-test-key",
            http_client=client,
        )

        with pytest.raises(ValueError) as exc_info:
            await notion_client.query_pages()

    assert len(requests) == 1
    assert "Notion request failed POST /v1/data_sources/ds_123/query: 400" in str(
        exc_info.value
    )
    assert "bad request" in str(exc_info.value)


@pytest.mark.asyncio
async def test_notion_client_retries_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._notion", raising=False)
    notion_module: Any = importlib.import_module("services.folk_notion_sync._notion")
    notion_client_class: Any = notion_module.NotionDataSourceClient
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                500,
                headers={"Retry-After": "not-a-number"},
                json={"error": "temporary"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"results": [], "has_more": False},
            request=request,
        )

    monkeypatch.setattr(notion_module.asyncio, "sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        notion_client = notion_client_class(
            _settings(max_retries=1),
            api_key="notion-test-key",
            http_client=client,
        )

        pages = await notion_client.query_pages()

    assert pages == []
    assert len(requests) == 2
    assert sleeps == [1.0]


def test_notion_id_tokens_do_not_match_substrings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_secret_stub(monkeypatch)
    monkeypatch.delitem(sys.modules, "services.folk_notion_sync._notion", raising=False)
    notion_module: Any = importlib.import_module("services.folk_notion_sync._notion")
    id_tokens: Any = notion_module._id_tokens

    tokens = id_tokens("obj_123\nobj_456")

    assert "obj_123" in tokens
    assert "obj_12" not in tokens


@pytest.mark.asyncio
async def test_send_sync_failure_alert_posts_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[dict[str, Any]] = []

    async def fake_send_slack_message(
        blocks: list[dict[str, Any]],
        channel: str,
        text_fallback: str = "New message",
    ) -> dict[str, Any]:
        messages.append(
            {"blocks": blocks, "channel": channel, "text_fallback": text_fallback}
        )
        return {"status": "success"}

    alerts = _alerts_module_with_slack_stub(monkeypatch, fake_send_slack_message)
    send_sync_failure_alert: Any = alerts.send_sync_failure_alert

    await send_sync_failure_alert(
        _settings(),
        title="object.updated for obj_123",
        detail="notion rejected request",
        event_id="evt_123",
        event_type="object.updated",
    )

    assert messages[0]["channel"] == "#folk-alerts"
    assert messages[0]["text_fallback"] == (
        "Folk -> Notion sync failed: object.updated for obj_123"
    )


@pytest.mark.asyncio
async def test_send_sync_failure_alert_logs_slack_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_send_slack_message(
        blocks: list[dict[str, Any]],
        channel: str,
        text_fallback: str = "New message",
    ) -> dict[str, Any]:
        _ = blocks, channel, text_fallback
        return {"status": "error", "message": "channel_not_found"}

    alerts = _alerts_module_with_slack_stub(monkeypatch, fake_send_slack_message)
    send_sync_failure_alert: Any = alerts.send_sync_failure_alert
    caplog.set_level("ERROR")

    await send_sync_failure_alert(
        _settings(),
        title="object.updated for obj_123",
        detail="notion rejected request",
        event_id="evt_123",
        event_type="object.updated",
    )

    assert "Slack alert send returned error" in caplog.text


@pytest.mark.asyncio
async def test_send_sync_failure_alert_logs_slack_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_send_slack_message(
        blocks: list[dict[str, Any]],
        channel: str,
        text_fallback: str = "New message",
    ) -> dict[str, Any]:
        _ = blocks, channel, text_fallback
        raise RuntimeError("slack unavailable")

    alerts = _alerts_module_with_slack_stub(monkeypatch, fake_send_slack_message)
    send_sync_failure_alert: Any = alerts.send_sync_failure_alert
    caplog.set_level("ERROR")

    await send_sync_failure_alert(
        _settings(),
        title="object.updated for obj_123",
        detail="notion rejected request",
        event_id="evt_123",
        event_type="object.updated",
    )

    assert "Failed to send Slack alert" in caplog.text


def test_folk_notion_sync_settings_requires_data_source_when_enabled() -> None:
    with pytest.raises(ValueError, match="NOTION_DATA_SOURCE_ID"):
        FolkNotionSyncSettings(enabled=True)


def test_get_folk_notion_sync_settings_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_module: Any = importlib.import_module(
        "services.folk_notion_sync._settings"
    )
    get_settings: Any = settings_module.get_folk_notion_sync_settings
    get_settings.cache_clear()
    monkeypatch.setenv("FOLK_NOTION_SYNC_ENABLED", "true")
    monkeypatch.setenv("FOLK_NOTION_SYNC_NOTION_DATA_SOURCE_ID", "ds_from_env")

    settings = get_settings()

    assert settings.enabled
    assert settings.notion_data_source_id == "ds_from_env"
    get_settings.cache_clear()


def _alerts_module_with_slack_stub(
    monkeypatch: pytest.MonkeyPatch,
    send_slack_message: Any,
) -> Any:
    fake_slack_service: Any = types.ModuleType("services.slack_service")
    fake_slack_service.get_slack_channel_from_env_key = lambda _env_key: "#folk-alerts"
    fake_slack_service.send_slack_message = send_slack_message

    loaded_alerts = sys.modules.get("services.folk_notion_sync._alerts")
    if loaded_alerts is not None:
        monkeypatch.setattr(loaded_alerts, "slack_service", fake_slack_service)
        return loaded_alerts

    services_package = importlib.import_module("services")
    monkeypatch.setattr(
        services_package, "slack_service", fake_slack_service, raising=False
    )
    monkeypatch.setitem(sys.modules, "services.slack_service", fake_slack_service)
    alerts = importlib.import_module("services.folk_notion_sync._alerts")
    monkeypatch.setattr(alerts, "slack_service", fake_slack_service)
    return alerts


def _install_secret_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_secret: Any = types.ModuleType("utils.secret")
    fake_secret.get_server_secret_with_fallback = lambda _key: "test-secret"
    fake_secret.get_client_secret_with_fallback = lambda _key: "test-secret"
    monkeypatch.setitem(sys.modules, "utils.secret", fake_secret)


def _settings(
    max_retries: int = 0,
    *,
    enabled: bool = True,
) -> FolkNotionSyncSettings:
    return FolkNotionSyncSettings(
        enabled=enabled,
        notion_data_source_id="ds_123",
        max_retries=max_retries,
    )


def _event(event_type: str) -> FolkWebhookEvent:
    return FolkWebhookEvent(
        id="evt_123",
        type=event_type,
        created_at="2026-06-18T12:00:00.000Z",
        resource_id="obj_123",
        resource_url="https://api.folk.app/v1/groups/grp_test/Deals/obj_123",
        payload={},
    )


def _deal() -> dict[str, Any]:
    return {
        "id": "obj_123",
        "name": "Acme - Voice AI",
        "companies": [{"id": "com_123", "name": "Acme"}],
        "customFieldValues": {"Stage": "1. Warm Lead (Sales)"},
    }


def _company() -> dict[str, Any]:
    return {
        "id": "com_123",
        "name": "Acme",
        "customFieldValues": {},
    }


def _projection(
    *,
    company_id: str,
    deal_id: str = "obj_123",
    name: str = "Acme",
) -> CompanyProjection:
    return CompanyProjection(
        key=company_id or name,
        name=name,
        company_id=company_id,
        deals=[
            DealProjection(
                id=deal_id,
                name="Acme - Voice AI",
                company_id=company_id,
                company_name=name,
                stage="1. Warm Lead (Sales)",
                ae="",
                fde="",
                product="",
                vendors="",
                total_locations="",
                deal_locations="",
                live_locations="",
                contract_signed_date="",
                go_live_date="",
                lead_source="",
                billing_details="",
                billing_method="",
                billing_status="",
                brand_structure="",
                key_account="",
                carr="",
                price_per_month_per_location="",
            )
        ],
        industry="",
        cuisine_type="",
        description="",
        addresses="",
        emails="",
        phones="",
        urls="",
        primary_contacts="",
    )


def _notion_page(
    page_id: str,
    *,
    company_ids: str = "",
    deal_ids: str = "",
    name: str = "",
    account_name: str = "",
) -> dict[str, Any]:
    return {
        "id": page_id,
        "properties": {
            "Folk Company IDs": _rich_text(company_ids),
            "Folk Deal IDs": _rich_text(deal_ids),
            "Name": _title(name),
            "account_name": {"select": {"name": account_name}} if account_name else {},
        },
    }


def _rich_text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"plain_text": value}]} if value else {"rich_text": []}


def _title(value: str) -> dict[str, Any]:
    return {"title": [{"plain_text": value}]} if value else {"title": []}


def json_body(request: httpx.Request) -> dict[str, Any]:
    import json

    value = json.loads(request.content.decode("utf-8"))
    return value if isinstance(value, dict) else {}
