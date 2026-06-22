from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

import utils.cache.tool_result_cache as tool_result_cache
from utils.cache.redis import RedisCacheSettings
from utils.cache.tool_result_cache import (
    PREVIOUS_TOOL_RESULT_SCHEMA,
    append_tool_result,
    build_cacheable_tool_result,
    build_raw_tool_result,
    build_tool_result_cache_key,
    close_tool_result_cache_client,
    get_tool_result_cache_client,
    get_tool_results,
)


def _with_tool_result(expected: dict[str, Any]) -> dict[str, Any]:
    cacheable_result = expected.get("cacheable_result")
    if cacheable_result is None:
        return expected
    return {**expected, "tool_result": cacheable_result}


def _raw_payload(
    *,
    tool_name: str = "toast_takeout_create_order_v1",
    raw_result: str = '{"status":"success"}',
    captured_at: str = "2026-06-22T20:00:00Z",
) -> dict[str, Any]:
    return {
        "schema": PREVIOUS_TOOL_RESULT_SCHEMA,
        "tool_name": tool_name,
        "raw_result": raw_result,
        "captured_at": captured_at,
    }


def test_build_tool_result_cache_key() -> None:
    assert (
        build_tool_result_cache_key("conversation-1")
        == "tool-results:v1:conversation-1"
    )


def test_build_raw_tool_result_preserves_exact_output() -> None:
    payload = {
        "schema": PREVIOUS_TOOL_RESULT_SCHEMA,
        "tool_name": " send_support_email ",
        "raw_result": "Email sent successfully.",
        "captured_at": "2026-06-22T20:00:00Z",
        "ignored": {"customer_phone": "+15551234567"},
    }

    assert build_raw_tool_result(payload) == {
        "schema": PREVIOUS_TOOL_RESULT_SCHEMA,
        "tool_name": "send_support_email",
        "raw_result": "Email sent successfully.",
        "captured_at": "2026-06-22T20:00:00Z",
    }


def test_build_raw_tool_result_rejects_invalid_payloads() -> None:
    assert build_raw_tool_result({"tool_name": "x", "raw_result": "ok"}) is None
    assert (
        build_raw_tool_result(
            {
                "schema": PREVIOUS_TOOL_RESULT_SCHEMA,
                "tool_name": "",
                "raw_result": "ok",
            }
        )
        is None
    )
    assert (
        build_raw_tool_result(
            {
                "schema": PREVIOUS_TOOL_RESULT_SCHEMA,
                "tool_name": "x",
                "raw_result": {"status": "ok"},
            }
        )
        is None
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

    assert result == _with_tool_result(
        {
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
    )


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

    assert result == _with_tool_result(
        {
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
    )


def test_build_cacheable_tool_result_keeps_toast_lookup_envelope() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "get_toast_item_details_v3",
            "result_summary": "toast lookup completed with status success.",
            "cacheable_result": {
                "kind": "toast_item_lookup_v3",
                "results": [
                    {
                        "request": {
                            "item_name": "Prototype Pizza",
                            "targets": [{"path_prefix": [], "group_name": "Toppings"}],
                            "customer_phone": "+15551234567",
                        },
                        "status": "ok",
                        "error_code": None,
                        "message": None,
                        "groups": [
                            {
                                "group_name": "Toppings",
                                "selection_state": "optional",
                                "options": [
                                    {
                                        "option_name": "Pepperoni",
                                        "price": 1.5,
                                        "specialInstructions": "drop notes",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "customer_email": "drop@example.com",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "get_toast_item_details_v3",
            "result_summary": "toast lookup completed with status success.",
            "cacheable_result": {
                "kind": "toast_item_lookup_v3",
                "results": [
                    {
                        "request": {
                            "item_name": "Prototype Pizza",
                            "targets": [{"path_prefix": [], "group_name": "Toppings"}],
                        },
                        "status": "ok",
                        "groups": [
                            {
                                "group_name": "Toppings",
                                "selection_state": "optional",
                                "options": [{"option_name": "Pepperoni", "price": 1.5}],
                            }
                        ],
                    }
                ],
            },
        }
    )


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

    assert result == _with_tool_result(
        {
            "tool_name": "adora_process_order",
            "status": "success",
            "cacheable_result": {
                "orderID": 12345,
                "orderNo": 67890,
                "processStatus": "paid",
                "trackerURL": "https://example.com/track/12345",
            },
        }
    )


def test_build_cacheable_tool_result_preserves_adora_order_parity_fields() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "validate_adora_order_intent",
            "status": "success",
            "cacheable_result": {
                "status": "success",
                "orderID": 12345,
                "orderNo": 67890,
                "processStatus": "paid",
                "trackerURL": "https://example.com/track/12345",
                "paymentUrl": "https://pay.example/secret",
                "customerName": "Drop Customer",
                "customer_email": "drop@example.com",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "validate_adora_order_intent",
            "status": "success",
            "cacheable_result": {
                "status": "success",
                "orderID": 12345,
                "orderNo": 67890,
                "processStatus": "paid",
                "trackerURL": "https://example.com/track/12345",
                "paymentUrl": "https://pay.example/secret",
                "customerName": "Drop Customer",
            },
        }
    )


def test_build_cacheable_tool_result_preserves_adora_delivery_zone_context() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "verify_adora_delivery_zone_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "adora_delivery_zone_check",
                "status": "success",
                "is_in_delivery_zone": True,
                "checked_delivery_address": {
                    "street_number": "123",
                    "street_name": "Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip": "78701",
                },
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "verify_adora_delivery_zone_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "adora_delivery_zone_check",
                "status": "success",
                "is_in_delivery_zone": True,
                "checked_delivery_address": {
                    "street_number": "123",
                    "street_name": "Main St",
                    "city": "Austin",
                    "state": "TX",
                    "zip": "78701",
                },
            },
        }
    )


def test_build_cacheable_tool_result_preserves_prefetch_timing_context() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "adora_wait_time_prefetch_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "adora_wait_time_prefetch_v1",
                "takeout_minutes": 20,
                "delivery_minutes": 30,
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "adora_wait_time_prefetch_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "adora_wait_time_prefetch_v1",
                "takeout_minutes": 20,
                "delivery_minutes": 30,
            },
        }
    )


def test_build_cacheable_tool_result_preserves_prefetch_profile_context() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "adora_customer_profile_prefetch_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "adora_customer_profile_prefetch_v1",
                "first_name": "Alice",
                "last_name": "Jones",
                "loyalty_member": True,
                "loyalty_point_count": 50,
                "delivery_address": {
                    "address": "123 Main St",
                    "city": "Austin",
                },
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "adora_customer_profile_prefetch_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "adora_customer_profile_prefetch_v1",
                "first_name": "Alice",
                "last_name": "Jones",
                "loyalty_member": True,
                "loyalty_point_count": 50,
                "delivery_address": {
                    "address": "123 Main St",
                    "city": "Austin",
                },
            },
        }
    )


def test_build_cacheable_tool_result_uses_minitable_family_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "minitable_make_reservation",
            "status": "confirmed",
            "cacheable_result": {
                "status": "confirmed",
                "booking_id": "booking-1",
                "restaurant_id": "restaurant-1",
                "party_size": 4,
                "date": "2026-06-16",
                "time": "18:30",
                "status_link": "https://example.com/reservations/booking-1",
                "guest_name": "Drop Guest",
                "customer_email": "drop@example.com",
                "notes": "drop free-form note",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "minitable_make_reservation",
            "status": "confirmed",
            "cacheable_result": {
                "status": "confirmed",
                "booking_id": "booking-1",
                "restaurant_id": "restaurant-1",
                "party_size": 4,
                "date": "2026-06-16",
                "time": "18:30",
                "status_link": "https://example.com/reservations/booking-1",
            },
        }
    )


def test_build_cacheable_tool_result_uses_olo_lookup_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "lookup_olo_order_options_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "olo_order_option_lookup_v1",
                "results": [
                    {
                        "status": "ok",
                        "query": {
                            "item_text": "Cheeseburger",
                            "customer_phone": "+15551234567",
                        },
                        "items": [
                            {
                                "item_name": "MOOYAH Cheeseburger",
                                "item_handle": "item:mooyah-cheeseburger:82610566",
                                "terminal_selections": [
                                    {
                                        "path_label": "Meal > Side Choice > Fries",
                                        "selection_handle": "sel:fries:1",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "payment_token": "drop-token",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "lookup_olo_order_options_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "olo_order_option_lookup_v1",
                "results": [
                    {
                        "status": "ok",
                        "query": {"item_text": "Cheeseburger"},
                        "items": [
                            {
                                "item_name": "MOOYAH Cheeseburger",
                                "item_handle": "item:mooyah-cheeseburger:82610566",
                                "terminal_selections": [
                                    {
                                        "path_label": "Meal > Side Choice > Fries",
                                        "selection_handle": "sel:fries:1",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }
    )


def test_build_cacheable_tool_result_uses_olo_order_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "olo_create_order_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "olo_order_validation_v1",
                "status": "success",
                "order_submitted": False,
                "basket_id": "basket-123",
                "validation": {"total": 22.81, "payment_url": "drop"},
                "customer_email": "drop@example.com",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "olo_create_order_v1",
            "status": "success",
            "cacheable_result": {
                "kind": "olo_order_validation_v1",
                "status": "success",
                "order_submitted": False,
                "basket_id": "basket-123",
                "validation": {"total": 22.81},
            },
        }
    )


def test_build_cacheable_tool_result_uses_transfer_family_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "call_transfer",
            "status": "success",
            "cacheable_result": {
                "status": "success",
                "purpose": "billing",
                "phone_number": "+15551234567",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "call_transfer",
            "status": "success",
            "cacheable_result": {"status": "success", "purpose": "billing"},
        }
    )


def test_build_cacheable_tool_result_uses_yelp_family_allowlist() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "yelp_make_reservation_no_cc",
            "status": "confirmed",
            "cacheable_result": {
                "status": "confirmed",
                "reservation_id": "yelp-1",
                "party_size": 2,
                "date": "2026-06-18",
                "time": "19:00",
                "customer_email": "drop@example.com",
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "yelp_make_reservation_no_cc",
            "status": "confirmed",
            "cacheable_result": {
                "status": "confirmed",
                "reservation_id": "yelp-1",
                "party_size": 2,
                "date": "2026-06-18",
                "time": "19:00",
            },
        }
    )


def test_build_cacheable_tool_result_preserves_email_string_tool_result() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "send_support_email",
            "status": "success",
            "tool_result": "Email sent successfully.",
        }
    )

    assert result == {
        "tool_name": "send_support_email",
        "status": "success",
        "cacheable_result": "Email sent successfully.",
        "tool_result": "Email sent successfully.",
    }


def test_build_cacheable_tool_result_preserves_structured_error_context() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "toast_takeout_create_order_v1",
            "status": "error",
            "error_type": "missing_params",
            "cacheable_result": {
                "status": "error",
                "source": "tool_handler",
                "error_type": "missing_params",
                "missing": ["items"],
                "retryable": True,
                "arguments": {"customer_phone": "+15551234567"},
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "toast_takeout_create_order_v1",
            "status": "error",
            "error_type": "missing_params",
            "cacheable_result": {
                "status": "error",
                "source": "tool_handler",
                "error_type": "missing_params",
                "missing": ["items"],
                "retryable": True,
            },
        }
    )


def test_build_cacheable_tool_result_preserves_safe_error_arguments() -> None:
    result = build_cacheable_tool_result(
        {
            "tool_name": "toast_takeout_create_order_v1",
            "status": "error",
            "error_type": "missing_params",
            "cacheable_result": {
                "status": "error",
                "source": "tool_handler",
                "error_type": "missing_params",
                "error": "Missing required parameters: ['customer_name']",
                "arguments": {"other": "value", "customer_phone": "+15551234567"},
                "missing": ["customer_name"],
            },
        }
    )

    assert result == _with_tool_result(
        {
            "tool_name": "toast_takeout_create_order_v1",
            "status": "error",
            "error_type": "missing_params",
            "cacheable_result": {
                "status": "error",
                "source": "tool_handler",
                "error_type": "missing_params",
                "error": "Missing required parameters: ['customer_name']",
                "arguments": {"other": "value"},
                "missing": ["customer_name"],
            },
        }
    )


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

    assert result == _with_tool_result(
        {
            "tool_name": "check_hours",
            "result_summary": "The store is open.",
            "cacheable_result": {
                "status": "open",
                "count": 1,
            },
        }
    )


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

    assert result == _with_tool_result(
        {
            "tool_name": "toast_v3",
            "cacheable_result": {"ok": True},
        }
    )


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
async def test_append_tool_result_writes_raw_payload_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    payload = _raw_payload(raw_result='{"status":"success","phone":"+15551234567"}')

    await append_tool_result("conversation-1", payload)

    assert fake_client.rpush_calls[0][0] == "tool-results:v1:conversation-1"
    assert json.loads(fake_client.rpush_calls[0][1]) == payload
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
        _raw_payload(),
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
        _raw_payload(raw_result="x" * 100),
    )

    assert fake_client.rpush_calls == []
    assert metrics[-1] == (
        "tool_result_cache.operation",
        {"operation": "append", "outcome": "skipped", "reason": "too_large"},
    )


@pytest.mark.asyncio
async def test_append_tool_result_ignores_unrelated_fields_before_size_limit(
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
            **_raw_payload(raw_result="ok"),
            "ignored_large_field": "x" * 5000,
        },
    )

    assert json.loads(fake_client.rpush_calls[0][1]) == _raw_payload(raw_result="ok")
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

    payload = _raw_payload(
        tool_name="adora_process_order",
        raw_result='{"orderID":12345,"processStatus":"paid","paymentToken":"kept"}',
    )

    await append_tool_result("conversation-1", payload)

    results = await get_tool_results("conversation-1")

    assert writer_client.rpush_calls
    assert reader_client.lrange_calls == [("tool-results:v1:conversation-1", 0, -1)]
    assert results == [payload]


@pytest.mark.asyncio
async def test_append_tool_result_skips_when_cache_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, None, metrics=metrics)

    await append_tool_result(
        "conversation-1",
        _raw_payload(),
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
        _raw_payload(),
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
        _raw_payload(),
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
                _raw_payload(tool_name="send_support_email", raw_result="Sent.")
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
        _raw_payload(tool_name="send_support_email", raw_result="Sent."),
        _with_tool_result(
            {"tool_name": "adora_v3", "cacheable_result": {"status": "success"}}
        ),
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
