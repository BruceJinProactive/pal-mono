from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from datetime import date, datetime
from types import TracebackType
from typing import Any, Protocol, Self, cast

from utils.cache.redis import (
    close_redis_cache_client,
    get_redis_cache_client,
    get_redis_cache_settings,
)
from utils.otel import increment_counter

logger = logging.getLogger("pal-mono")

TOOL_RESULT_CACHE_KEY_PREFIX = "tool-results:v1"
TOOL_RESULT_CACHE_OPERATION_METRIC = "tool_result_cache.operation"

_ALLOWED_TOP_LEVEL_FIELDS = {
    "tool_name",
    "input_summary",
    "result_summary",
    "cacheable_result",
    "status",
    "error_type",
    "captured_at",
}
_SENSITIVE_KEY_PARTS = (
    "address",
    "api_key",
    "auth",
    "card",
    "comment",
    "credit",
    "customer",
    "cvc",
    "cvv",
    "email",
    "first_name",
    "full_name",
    "guest",
    "instruction",
    "last_name",
    "memo",
    "note",
    "password",
    "payment",
    "phone",
    "remark",
    "secret",
    "special_request",
    "specialrequest",
    "token",
)
_MAX_SANITIZE_DEPTH = 6

_COMMON_CACHEABLE_RESULT_FIELDS = frozenset(
    {
        "count",
        "error",
        "error_code",
        "error_type",
        "errorCode",
        "errorType",
        "message",
        "ok",
        "state",
        "status",
        "success",
    }
)
_TOAST_CACHEABLE_RESULT_FIELDS = _COMMON_CACHEABLE_RESULT_FIELDS | frozenset(
    {
        "cart_id",
        "cartId",
        "check_id",
        "checkId",
        "dining_option",
        "diningOption",
        "estimated_ready_time",
        "estimatedReadyTime",
        "fulfillment_state",
        "fulfillment_status",
        "fulfillmentState",
        "fulfillmentStatus",
        "items",
        "order_guid",
        "order_id",
        "order_number",
        "order_state",
        "order_status",
        "orderGuid",
        "orderId",
        "orderNumber",
        "orderState",
        "orderStatus",
        "pickup_time",
        "pickupTime",
    }
)
_TOAST_LOOKUP_TOOL_NAMES = frozenset({"get_toast_item_details_v3"})
_TOAST_LOOKUP_CACHEABLE_RESULT_FIELDS = _TOAST_CACHEABLE_RESULT_FIELDS | frozenset(
    {
        "kind",
        "results",
    }
)
_ADORA_CACHEABLE_RESULT_FIELDS = _COMMON_CACHEABLE_RESULT_FIELDS | frozenset(
    {
        "available",
        "availability",
        "key",
        "online_ordering_status",
        "onlineOrderingStatus",
        "order_id",
        "order_no",
        "order_number",
        "order_status",
        "orderId",
        "orderID",
        "orderNo",
        "orderNumber",
        "orderStatus",
        "process_status",
        "processStatus",
        "trackerURL",
        "tracking_link",
        "trackingLink",
    }
)
_CACHEABLE_RESULT_FIELDS_BY_TOOL_FAMILY = {
    "adora": _ADORA_CACHEABLE_RESULT_FIELDS,
    "generic": _COMMON_CACHEABLE_RESULT_FIELDS,
    "toast": _TOAST_CACHEABLE_RESULT_FIELDS,
}


class ToolResultRedisClient(Protocol):
    def pipeline(self, transaction: bool = True) -> ToolResultRedisPipeline: ...

    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]: ...


class ToolResultRedisPipeline(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    def rpush(self, name: str, *values: str) -> object: ...

    def expire(self, name: str, time: int) -> object: ...

    async def execute(self) -> object: ...


def build_tool_result_cache_key(conversation_id: str) -> str:
    return f"{TOOL_RESULT_CACHE_KEY_PREFIX}:{conversation_id}"


async def get_tool_result_cache_client() -> ToolResultRedisClient | None:
    client = await get_redis_cache_client()
    return cast(ToolResultRedisClient | None, client)


async def close_tool_result_cache_client() -> None:
    await close_redis_cache_client()


async def append_tool_result(
    conversation_id: str,
    payload: Mapping[str, Any],
) -> None:
    try:
        if not conversation_id:
            _log_cache_event("append", "skipped", reason="missing_conversation_id")
            return

        settings = get_redis_cache_settings()
        cacheable_payload = build_cacheable_tool_result(payload)
        if cacheable_payload is None:
            _log_cache_event("append", "skipped", reason="not_cacheable")
            return

        serialized = json.dumps(
            cacheable_payload,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        size_bytes = len(serialized.encode("utf-8"))
        if size_bytes > settings.max_item_bytes:
            _log_cache_event(
                "append",
                "skipped",
                reason="too_large",
                item_bytes=size_bytes,
            )
            return

        client = await get_tool_result_cache_client()
        if client is None:
            _log_cache_event("append", "skipped", reason="disabled")
            return

        key = build_tool_result_cache_key(conversation_id)
        async with client.pipeline(transaction=True) as pipe:
            pipe.rpush(key, serialized)
            pipe.expire(key, settings.default_ttl_seconds)
            await pipe.execute()
        _log_cache_event(
            "append",
            "success",
            result_count=1,
            item_bytes=size_bytes,
        )
    except Exception:
        logger.warning(
            "Tool result cache append failed",
            extra={"operation": "append", "outcome": "error"},
            exc_info=True,
        )
        _emit_cache_metric("append", "error")


async def get_tool_results(conversation_id: str) -> list[dict[str, Any]]:
    try:
        if not conversation_id:
            _log_cache_event("get", "miss", reason="missing_conversation_id")
            return []

        client = await get_tool_result_cache_client()
        if client is None:
            _log_cache_event("get", "miss", reason="disabled")
            return []

        key = build_tool_result_cache_key(conversation_id)
        raw_items = await client.lrange(key, 0, -1)
        results: list[dict[str, Any]] = []
        malformed_count = 0

        for raw_item in raw_items:
            parsed = _parse_cached_item(raw_item)
            if parsed is None:
                malformed_count += 1
                continue
            results.append(parsed)

        _log_cache_event(
            "get",
            "hit" if results else "miss",
            result_count=len(results),
            malformed_count=malformed_count,
        )
        return results
    except Exception:
        logger.warning(
            "Tool result cache read failed",
            extra={"operation": "get", "outcome": "error"},
            exc_info=True,
        )
        _emit_cache_metric("get", "error")
        return []


def build_cacheable_tool_result(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    tool_name = _sanitize_text(payload.get("tool_name"))
    if not tool_name:
        return None

    result: dict[str, Any] = {"tool_name": tool_name}

    for field in _ALLOWED_TOP_LEVEL_FIELDS - {"tool_name", "cacheable_result"}:
        if field not in payload:
            continue
        value = payload[field]
        if field == "error_type" and value is None:
            result[field] = None
            continue
        sanitized_value = _sanitize_json_value(value)
        if sanitized_value is not None:
            result[field] = sanitized_value

    if "cacheable_result" in payload:
        cacheable_result = _sanitize_cacheable_result(
            tool_name,
            payload["cacheable_result"],
        )
        if cacheable_result is not None:
            result["cacheable_result"] = cacheable_result

    if not any(
        field in result for field in ("cacheable_result", "result_summary", "status")
    ):
        return None

    return result


def _parse_cached_item(raw_item: str | bytes) -> dict[str, Any] | None:
    try:
        if isinstance(raw_item, bytes):
            raw_item = raw_item.decode("utf-8")
        parsed = json.loads(raw_item)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, Mapping):
        return None

    return build_cacheable_tool_result(parsed)


def _sanitize_cacheable_result(tool_name: str, value: Any) -> Any:
    if not isinstance(value, Mapping):
        return _sanitize_json_value(value)

    allowed_fields = _cacheable_result_fields_for_tool(tool_name)
    sanitized_mapping: dict[str, Any] = {}
    for key, nested_value in value.items():
        if (
            not isinstance(key, str)
            or key not in allowed_fields
            or _is_sensitive_key(key)
        ):
            continue
        sanitized_value = _sanitize_json_value(nested_value)
        if sanitized_value is not None:
            sanitized_mapping[key] = sanitized_value

    return sanitized_mapping or None


def _cacheable_result_fields_for_tool(tool_name: str) -> frozenset[str]:
    family = _tool_family_for_name(tool_name)
    if family == "toast" and tool_name.lower() in _TOAST_LOOKUP_TOOL_NAMES:
        return _TOAST_LOOKUP_CACHEABLE_RESULT_FIELDS
    return _CACHEABLE_RESULT_FIELDS_BY_TOOL_FAMILY[family]


def _tool_family_for_name(tool_name: str) -> str:
    normalized_tool_name = tool_name.lower()
    if "toast" in normalized_tool_name:
        return "toast"
    if "adora" in normalized_tool_name:
        return "adora"
    return "generic"


def _sanitize_json_value(value: Any, depth: int = 0) -> Any:
    if depth > _MAX_SANITIZE_DEPTH:
        return None

    if value is None or isinstance(value, bool | str):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, datetime | date):
        return value.isoformat()

    if isinstance(value, Mapping):
        sanitized_mapping: dict[str, Any] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str) or _is_sensitive_key(key):
                continue
            sanitized_value = _sanitize_json_value(nested_value, depth + 1)
            if sanitized_value is not None:
                sanitized_mapping[key] = sanitized_value
        return sanitized_mapping or None

    if isinstance(value, list | tuple):
        sanitized_items = [
            sanitized_value
            for item in value
            if (sanitized_value := _sanitize_json_value(item, depth + 1)) is not None
        ]
        return sanitized_items

    return None


def _sanitize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.lower()
    compact_key = "".join(
        character for character in normalized_key if character.isalnum()
    )
    return any(
        part in normalized_key or part.replace("_", "") in compact_key
        for part in _SENSITIVE_KEY_PARTS
    )


def _log_cache_event(
    operation: str,
    outcome: str,
    *,
    reason: str = "",
    result_count: int | None = None,
    malformed_count: int | None = None,
    item_bytes: int | None = None,
) -> None:
    log_payload: dict[str, Any] = {
        "operation": operation,
        "outcome": outcome,
    }
    metric_reason = reason

    if reason:
        log_payload["reason"] = reason
    if result_count is not None:
        log_payload["result_count"] = result_count
    if malformed_count is not None:
        log_payload["malformed_count"] = malformed_count
        if malformed_count and not metric_reason:
            metric_reason = "malformed_entries"
    if item_bytes is not None:
        log_payload["item_bytes"] = item_bytes

    logger.info("Tool result cache operation", extra=log_payload)
    _emit_cache_metric(operation, outcome, reason=metric_reason)


def _emit_cache_metric(operation: str, outcome: str, *, reason: str = "") -> None:
    attributes = {
        "operation": operation,
        "outcome": outcome,
    }
    if reason:
        attributes["reason"] = reason

    try:
        increment_counter(TOOL_RESULT_CACHE_OPERATION_METRIC, attributes=attributes)
    except Exception:
        logger.debug(
            "Tool result cache metric emission failed",
            extra={"operation": operation, "outcome": outcome},
            exc_info=True,
        )
