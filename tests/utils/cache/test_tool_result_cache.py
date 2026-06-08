from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import utils.cache.tool_result_cache as tool_result_cache
from utils.cache.redis import RedisCacheSettings
from utils.cache.tool_result_cache import (
    append_tool_result,
    build_cacheable_tool_result,
    build_tool_result_cache_key,
    close_tool_result_cache_client,
    get_tool_result_cache_client,
    get_tool_results,
)


def test_build_tool_result_cache_key() -> None:
    assert (
        build_tool_result_cache_key("conversation-1")
        == "tool-results:v1:conversation-1"
    )


def test_build_cacheable_tool_result_allowlists_and_redacts() -> None:
    payload = {
        "tool_name": " toast_takeout_create_order_v1 ",
        "result_summary": "Order was created.",
        "status": "success",
        "error_type": None,
        "captured_at": datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc),
        "raw_result": {"secret": "do-not-cache"},
        "cacheable_result": {
            "order_state": "pending_payment",
            "customer_email": "drop@example.com",
            "items": [
                {"name": "pizza", "auth_token": "drop-me"},
                {"name": "salad", "quantity": 1},
            ],
            "score": float("nan"),
        },
    }

    result = build_cacheable_tool_result(payload)

    assert result == {
        "tool_name": "toast_takeout_create_order_v1",
        "result_summary": "Order was created.",
        "status": "success",
        "error_type": None,
        "captured_at": "2026-06-03T12:00:00+00:00",
        "cacheable_result": {
            "order_state": "pending_payment",
            "items": [
                {"name": "pizza"},
                {"name": "salad", "quantity": 1},
            ],
        },
    }


def test_build_cacheable_tool_result_uses_toast_family_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "toast_takeout_create_order_v1",
            "result_summary": "Order was created.",
            "cacheable_result": {
                "order_state": "pending_payment",
                "order_number": "10042",
                "reservation_status": "drop-non-toast-field",
                "customerName": "Drop Customer",
                "deliveryAddress": "123 Drop St",
                "items": [
                    {
                        "name": "pizza",
                        "quantity": 1,
                        "specialInstructions": "drop free-form text",
                    },
                    {
                        "name": "salad",
                        "auth_token": "drop-token",
                    },
                ],
            },
        }
    )

    assert result == {
        "tool_name": "toast_takeout_create_order_v1",
        "result_summary": "Order was created.",
        "cacheable_result": {
            "order_state": "pending_payment",
            "order_number": "10042",
            "items": [
                {"name": "pizza", "quantity": 1},
                {"name": "salad"},
            ],
        },
    }


def test_build_cacheable_tool_result_uses_adora_family_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "adora_process_order",
            "status": "success",
            "cacheable_result": {
                "orderID": 12345,
                "orderNo": 67890,
                "processStatus": "paid",
                "trackerURL": "https://example.com/track/12345",
                "reservation_status": "drop-reservation-field",
                "party_size": 4,
                "order_state": "drop-toast-field",
                "guestEmail": "drop@example.com",
                "guestNotes": "drop free-form text",
                "paymentUrl": "drop-payment-link",
            },
        }
    )

    assert result == {
        "tool_name": "adora_process_order",
        "status": "success",
        "cacheable_result": {
            "orderID": 12345,
            "orderNo": 67890,
            "processStatus": "paid",
            "trackerURL": "https://example.com/track/12345",
        },
    }


def test_build_cacheable_tool_result_uses_generic_family_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "check_hours",
            "result_summary": "The store is open.",
            "cacheable_result": {
                "status": "open",
                "count": 1,
                "order_state": "drop-toast-field",
                "reservation_status": "drop-adora-field",
                "phoneNumber": "drop-phone",
            },
        }
    )

    assert result == {
        "tool_name": "check_hours",
        "result_summary": "The store is open.",
        "cacheable_result": {
            "status": "open",
            "count": 1,
        },
    }


def test_build_cacheable_tool_result_requires_tool_name_and_useful_result() -> None:
    assert build_cacheable_tool_result({"result_summary": "missing tool"}) is None
    assert build_cacheable_tool_result({"tool_name": "toast_v3"}) is None


def test_build_cacheable_tool_result_drops_unsupported_and_deep_values() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "toast_v3",
            "cacheable_result": {
                "ok": True,
                "unsupported": object(),
                "deep": {
                    "a": {
                        "b": {
                            "c": {
                                "d": {
                                    "e": {
                                        "f": {
                                            "g": "too deep",
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
            },
        }
    )

    assert result == {
        "tool_name": "toast_v3",
        "cacheable_result": {"ok": True},
    }


@pytest.mark.asyncio
async def test_get_tool_result_cache_client_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()

    async def fake_get_redis_cache_client() -> _FakeRedisClient:
        return fake_client

    monkeypatch.setattr(
        tool_result_cache,
        "get_redis_cache_client",
        fake_get_redis_cache_client,
    )

    assert await get_tool_result_cache_client() is fake_client


@pytest.mark.asyncio
async def test_close_tool_result_cache_client_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_close_redis_cache_client() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        tool_result_cache,
        "close_redis_cache_client",
        fake_close_redis_cache_client,
    )

    await close_tool_result_cache_client()

    assert called is True


@pytest.mark.asyncio
async def test_append_tool_result_writes_sanitized_payload_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    await append_tool_result(
        "conversation-1",
        {
            "tool_name": "toast_takeout_create_order_v1",
            "input_summary": "Create order",
            "result_summary": "Order created",
            "status": "success",
            "raw_result": {"password": "drop"},
            "cacheable_result": {
                "order_state": "pending_payment",
                "phone_number": "drop",
            },
        },
    )

    assert fake_client.rpush_calls[0][0] == "tool-results:v1:conversation-1"
    assert json.loads(fake_client.rpush_calls[0][1]) == {
        "tool_name": "toast_takeout_create_order_v1",
        "input_summary": "Create order",
        "result_summary": "Order created",
        "status": "success",
        "cacheable_result": {"order_state": "pending_payment"},
    }
    assert fake_client.expire_calls == [("tool-results:v1:conversation-1", 1800)]
    assert fake_client.pipeline_transactions == [True]
    assert fake_client.pipeline_execute_count == 1
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "success"},
    )


@pytest.mark.asyncio
async def test_append_tool_result_skips_missing_conversation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    await append_tool_result(
        "",
        {"tool_name": "toast_v3", "result_summary": "Order created"},
    )

    assert fake_client.rpush_calls == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {
            "operation": "append",
            "outcome": "skipped",
            "reason": "missing_conversation_id",
        },
    )


@pytest.mark.asyncio
async def test_append_tool_result_skips_non_cacheable_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    _install_cache_fakes(monkeypatch, fake_client)

    await append_tool_result("conversation-1", {"tool_name": "toast_v3"})

    assert fake_client.rpush_calls == []
    assert fake_client.expire_calls == []


@pytest.mark.asyncio
async def test_append_tool_result_skips_oversized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(
        monkeypatch,
        fake_client,
        settings=RedisCacheSettings(
            enabled=True,
            host="cache.example.local",
            max_item_bytes=20,
        ),
        metrics=metrics,
    )

    await append_tool_result(
        "conversation-1",
        {
            "tool_name": "toast_v3",
            "result_summary": "This result is too large for the tiny test limit",
        },
    )

    assert fake_client.rpush_calls == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "skipped", "reason": "too_large"},
    )


@pytest.mark.asyncio
async def test_append_tool_result_applies_allowlist_before_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(
        monkeypatch,
        fake_client,
        settings=RedisCacheSettings(
            enabled=True,
            host="cache.example.local",
            max_item_bytes=256,
        ),
        metrics=metrics,
    )

    await append_tool_result(
        "conversation-1",
        {
            "tool_name": "toast_takeout_create_order_v1",
            "result_summary": "Order created",
            "cacheable_result": {
                "order_state": "created",
                "raw_payload": "x" * 5000,
            },
        },
    )

    assert json.loads(fake_client.rpush_calls[0][1]) == {
        "tool_name": "toast_takeout_create_order_v1",
        "result_summary": "Order created",
        "cacheable_result": {"order_state": "created"},
    }
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "success"},
    )


@pytest.mark.asyncio
async def test_tool_results_can_be_written_and_read_by_separate_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate one pod writing a tool result and another pod reading it."""
    shared_store: dict[str, list[str | bytes]] = {}
    writer_client = _FakeRedisClient(shared_store=shared_store)
    reader_client = _FakeRedisClient(shared_store=shared_store)
    cache_clients = [writer_client, reader_client]

    async def fake_get_tool_result_cache_client() -> _FakeRedisClient | None:
        return cache_clients.pop(0)

    monkeypatch.setattr(
        tool_result_cache,
        "get_tool_result_cache_client",
        fake_get_tool_result_cache_client,
    )

    def fake_get_redis_cache_settings() -> RedisCacheSettings:
        return RedisCacheSettings(enabled=True, host="cache.example.local")

    monkeypatch.setattr(
        tool_result_cache,
        "get_redis_cache_settings",
        fake_get_redis_cache_settings,
    )

    await append_tool_result(
        "conversation-1",
        {
            "tool_name": "adora_process_order",
            "result_summary": "Order was submitted.",
            "status": "success",
            "cacheable_result": {
                "orderID": 12345,
                "processStatus": "paid",
                "paymentToken": "drop-sensitive-token",
            },
        },
    )

    results = await get_tool_results("conversation-1")

    assert writer_client.rpush_calls
    assert reader_client.lrange_calls == [("tool-results:v1:conversation-1", 0, -1)]
    assert results == [
        {
            "tool_name": "adora_process_order",
            "result_summary": "Order was submitted.",
            "status": "success",
            "cacheable_result": {
                "orderID": 12345,
                "processStatus": "paid",
            },
        }
    ]


@pytest.mark.asyncio
async def test_append_tool_result_skips_when_cache_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, None, metrics=metrics)

    await append_tool_result(
        "conversation-1",
        {"tool_name": "toast_v3", "result_summary": "Order created"},
    )

    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "skipped", "reason": "disabled"},
    )


@pytest.mark.asyncio
async def test_append_tool_result_best_effort_on_redis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient(raise_on_rpush=True)
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    await append_tool_result(
        "conversation-1",
        {"tool_name": "toast_v3", "result_summary": "Order created"},
    )

    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "error"},
    )


@pytest.mark.asyncio
async def test_append_tool_result_best_effort_on_settings_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics: list[tuple[str, dict[str, str]]] = []

    def fake_get_redis_cache_settings() -> RedisCacheSettings:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(
        tool_result_cache,
        "get_redis_cache_settings",
        fake_get_redis_cache_settings,
    )

    def fake_increment_counter(name: str, attributes: dict[str, str]) -> None:
        metrics.append((name, attributes))

    monkeypatch.setattr(tool_result_cache, "increment_counter", fake_increment_counter)

    await append_tool_result(
        "conversation-1",
        {"tool_name": "toast_v3", "result_summary": "Order created"},
    )

    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "error"},
    )


@pytest.mark.asyncio
async def test_get_tool_results_parses_valid_entries_and_drops_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient(
        lrange_items=[
            json.dumps(
                {
                    "tool_name": "toast_v3",
                    "result_summary": "Order created",
                    "raw_result": {"secret": "drop"},
                }
            ),
            "not-json",
            json.dumps(["not", "an", "object"]),
            b'{"tool_name":"adora_v3","cacheable_result":{"status":"success","email":"drop"}}',
            b"\xff",
        ]
    )
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    results = await get_tool_results("conversation-1")

    assert fake_client.lrange_calls == [("tool-results:v1:conversation-1", 0, -1)]
    assert results == [
        {"tool_name": "toast_v3", "result_summary": "Order created"},
        {"tool_name": "adora_v3", "cacheable_result": {"status": "success"}},
    ]
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "get", "outcome": "hit", "reason": "malformed_entries"},
    )


@pytest.mark.asyncio
async def test_get_tool_results_returns_empty_on_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient(lrange_items=[])
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    assert await get_tool_results("conversation-1") == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "get", "outcome": "miss"},
    )


@pytest.mark.asyncio
async def test_get_tool_results_returns_empty_without_conversation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    assert await get_tool_results("") == []
    assert fake_client.lrange_calls == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "get", "outcome": "miss", "reason": "missing_conversation_id"},
    )


@pytest.mark.asyncio
async def test_get_tool_results_returns_empty_when_cache_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, None, metrics=metrics)

    assert await get_tool_results("conversation-1") == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "get", "outcome": "miss", "reason": "disabled"},
    )


@pytest.mark.asyncio
async def test_get_tool_results_best_effort_on_redis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient(raise_on_lrange=True)
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    assert await get_tool_results("conversation-1") == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "get", "outcome": "error"},
    )


def test_metric_emission_failures_are_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_increment_counter(_: str, attributes: dict[str, str]) -> None:
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(
        tool_result_cache,
        "increment_counter",
        failing_increment_counter,
    )

    tool_result_cache._emit_cache_metric("append", "success")


def _install_cache_fakes(
    monkeypatch: pytest.MonkeyPatch,
    client: _FakeRedisClient | None,
    *,
    settings: RedisCacheSettings | None = None,
    metrics: list[tuple[str, dict[str, str]]] | None = None,
) -> None:
    async def fake_get_tool_result_cache_client() -> _FakeRedisClient | None:
        return client

    monkeypatch.setattr(
        tool_result_cache,
        "get_tool_result_cache_client",
        fake_get_tool_result_cache_client,
    )

    def fake_get_redis_cache_settings() -> RedisCacheSettings:
        return settings or RedisCacheSettings(
            enabled=True,
            host="cache.example.local",
        )

    monkeypatch.setattr(
        tool_result_cache,
        "get_redis_cache_settings",
        fake_get_redis_cache_settings,
    )

    if metrics is not None:

        def fake_increment_counter(name: str, attributes: dict[str, str]) -> None:
            metrics.append((name, attributes))

        monkeypatch.setattr(
            tool_result_cache,
            "increment_counter",
            fake_increment_counter,
        )


class _FakeRedisClient:
    def __init__(
        self,
        *,
        lrange_items: list[str | bytes] | None = None,
        shared_store: dict[str, list[str | bytes]] | None = None,
        raise_on_rpush: bool = False,
        raise_on_lrange: bool = False,
    ) -> None:
        self.lrange_items = lrange_items or []
        self.shared_store = shared_store
        self.raise_on_rpush = raise_on_rpush
        self.raise_on_lrange = raise_on_lrange
        self.rpush_calls: list[tuple[str, str]] = []
        self.expire_calls: list[tuple[str, int]] = []
        self.lrange_calls: list[tuple[str, int, int]] = []
        self.pipeline_transactions: list[bool] = []
        self.pipeline_execute_count = 0

    def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
        self.pipeline_transactions.append(transaction)
        return _FakeRedisPipeline(self)

    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]:
        if self.raise_on_lrange:
            raise RuntimeError("redis unavailable")
        self.lrange_calls.append((name, start, end))
        if self.shared_store is not None:
            stop = None if end == -1 else end + 1
            return self.shared_store.get(name, [])[start:stop]
        return self.lrange_items


class _FakeRedisPipeline:
    def __init__(self, client: _FakeRedisClient) -> None:
        self.client = client

    async def __aenter__(self) -> _FakeRedisPipeline:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def rpush(self, name: str, *values: str) -> object:
        if self.client.raise_on_rpush:
            raise RuntimeError("redis unavailable")
        for value in values:
            self.client.rpush_calls.append((name, value))
        if self.client.shared_store is not None:
            self.client.shared_store.setdefault(name, []).extend(values)
        return len(values)

    def expire(self, name: str, time: int) -> object:
        self.client.expire_calls.append((name, time))
        return True

    async def execute(self) -> object:
        self.client.pipeline_execute_count += 1
        return True
