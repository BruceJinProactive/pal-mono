from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self, cast

from services.vision_observation_service._smoothing import (
    EventGenerationConfig,
    SmoothingDecision,
    SmoothingObservation,
    append_smoothing_observation,
    build_smoothing_metadata,
    collect_ready_smoothing_decisions,
    mark_smoothing_finalized,
    smoothing_finalized_observed_at,
    smoothing_observation_rows,
)
from utils.cache.redis import get_redis_cache_client, get_redis_cache_settings
from utils.log import logger
from utils.otel import increment_counter

VISION_SMOOTHING_CACHE_OPERATION_METRIC = "vision_smoothing_cache.operation"

_CACHE_KEY_PREFIX = "vision-smoothing:v1"
_LOCK_TTL_SECONDS = 300
_LOCK_RETRY_ATTEMPTS = 3
_LOCK_RETRY_DELAY_SECONDS = 0.05
_MIN_TTL_SECONDS = 7200
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class VisionSmoothingRedisClient(Protocol):
    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]: ...

    async def get(self, name: str) -> str | bytes | None: ...

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> object: ...

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object: ...

    def pipeline(self, transaction: bool = True) -> VisionSmoothingRedisPipeline: ...


class VisionSmoothingRedisPipeline(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    def delete(self, *names: str) -> object: ...

    def rpush(self, name: str, *values: str) -> object: ...

    def set(self, name: str, value: str) -> object: ...

    def expire(self, name: str, time: int) -> object: ...

    async def execute(self) -> object: ...


@dataclass
class VisionSmoothingCacheBuffer:
    client: VisionSmoothingRedisClient
    entity_id: uuid.UUID
    camera_config_id: uuid.UUID
    definition_type: str
    config: EventGenerationConfig
    observation_key: str
    finalized_key: str
    lock_key: str
    lock_token: str
    metadata: dict[str, object]
    ttl_seconds: int

    def collect_ready_decisions(self, now: datetime) -> list[SmoothingDecision]:
        return collect_ready_smoothing_decisions(
            self.metadata,
            self.definition_type,
            self.config,
            now,
        )

    def mark_finalized(self, observed_at: datetime) -> None:
        self.metadata = mark_smoothing_finalized(
            self.metadata,
            self.definition_type,
            observed_at,
        )

    async def save(self) -> None:
        rows = smoothing_observation_rows(self.metadata, self.definition_type)
        finalized = smoothing_finalized_observed_at(
            self.metadata,
            self.definition_type,
        )
        serialized_rows = [
            json.dumps(row, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
            for row in rows
        ]

        try:
            async with self.client.pipeline(transaction=True) as pipe:
                pipe.delete(self.observation_key)
                if serialized_rows:
                    pipe.rpush(self.observation_key, *serialized_rows)
                pipe.expire(self.observation_key, self.ttl_seconds)
                if finalized is None:
                    pipe.delete(self.finalized_key)
                else:
                    pipe.set(self.finalized_key, finalized)
                    pipe.expire(self.finalized_key, self.ttl_seconds)
                await pipe.execute()
            _log_cache_event("save", "success", row_count=len(rows))
        except Exception:
            logger.warning(
                "[Vision Smoothing Cache] Failed to save smoothing buffer",
                extra={
                    "operation": "save",
                    "outcome": "error",
                    "entity_id": str(self.entity_id),
                    "camera_config_id": str(self.camera_config_id),
                    "definition_type": self.definition_type,
                },
                exc_info=True,
            )
            _emit_cache_metric("save", "error")
            raise

    async def release(self) -> None:
        try:
            await self.client.eval(
                _RELEASE_LOCK_SCRIPT,
                1,
                self.lock_key,
                self.lock_token,
            )
        except Exception:
            logger.warning(
                "[Vision Smoothing Cache] Failed to release lock",
                extra={
                    "operation": "release_lock",
                    "outcome": "error",
                    "entity_id": str(self.entity_id),
                    "camera_config_id": str(self.camera_config_id),
                    "definition_type": self.definition_type,
                },
                exc_info=True,
            )
            _emit_cache_metric("release_lock", "error")


async def acquire_smoothing_cache_buffer(
    entity_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    definition_type: str,
    observation: SmoothingObservation,
    config: EventGenerationConfig,
) -> VisionSmoothingCacheBuffer | None:
    try:
        if camera_config_id != observation.camera_config_id:
            raise ValueError("camera_config_id must match observation.camera_config_id")

        client = await get_vision_smoothing_cache_client()
        if client is None:
            _log_cache_event("acquire", "skipped", reason="disabled")
            return None

        observation_key = build_observations_key(
            entity_id,
            camera_config_id,
            definition_type,
        )
        finalized_key = build_finalized_key(
            entity_id,
            camera_config_id,
            definition_type,
        )
        lock_key = build_lock_key(entity_id, camera_config_id, definition_type)
        lock_token = str(uuid.uuid4())
        if not await _acquire_lock(client, lock_key, lock_token):
            _log_cache_event("acquire", "skipped", reason="lock_unavailable")
            return None

        try:
            raw_rows = await client.lrange(observation_key, 0, -1)
            finalized = await client.get(finalized_key)
            metadata = build_smoothing_metadata(
                definition_type=definition_type,
                observations=_parse_observation_rows(raw_rows),
                finalized_observed_at=_parse_optional_str(finalized),
            )
            metadata = append_smoothing_observation(
                metadata,
                definition_type,
                observation,
                config,
            )
            _log_cache_event("acquire", "success")
            return VisionSmoothingCacheBuffer(
                client=client,
                entity_id=entity_id,
                camera_config_id=camera_config_id,
                definition_type=definition_type,
                config=config,
                observation_key=observation_key,
                finalized_key=finalized_key,
                lock_key=lock_key,
                lock_token=lock_token,
                metadata=metadata,
                ttl_seconds=_ttl_seconds(config),
            )
        except Exception:
            await _release_lock(client, lock_key, lock_token)
            raise
    except Exception:
        logger.warning(
            "[Vision Smoothing Cache] Failed to acquire smoothing buffer",
            extra={
                "operation": "acquire",
                "outcome": "error",
                "entity_id": str(entity_id),
                "camera_config_id": str(camera_config_id),
                "definition_type": definition_type,
            },
            exc_info=True,
        )
        _emit_cache_metric("acquire", "error")
        return None


async def get_vision_smoothing_cache_client() -> VisionSmoothingRedisClient | None:
    client = await get_redis_cache_client()
    return cast(VisionSmoothingRedisClient | None, client)


def build_observations_key(
    entity_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    definition_type: str,
) -> str:
    return f"{_smoothing_key_prefix(entity_id, camera_config_id, definition_type)}:observations"


def build_finalized_key(
    entity_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    definition_type: str,
) -> str:
    return f"{_smoothing_key_prefix(entity_id, camera_config_id, definition_type)}:finalized"


def build_lock_key(
    entity_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    definition_type: str,
) -> str:
    return f"{_smoothing_key_prefix(entity_id, camera_config_id, definition_type)}:lock"


def _smoothing_key_prefix(
    entity_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    definition_type: str,
) -> str:
    # The hash tag keeps multi-key Redis transactions in one cluster hash slot.
    return (
        f"{_CACHE_KEY_PREFIX}:"
        f"{{entity:{entity_id}:camera:{camera_config_id}:type:{definition_type}}}"
    )


def _ttl_seconds(config: EventGenerationConfig) -> int:
    try:
        default_ttl = get_redis_cache_settings().default_ttl_seconds
    except Exception:
        default_ttl = 0
    return max(default_ttl, config.max_frame_gap_seconds * 2, _MIN_TTL_SECONDS)


async def _acquire_lock(
    client: VisionSmoothingRedisClient,
    lock_key: str,
    lock_token: str,
) -> bool:
    for attempt in range(_LOCK_RETRY_ATTEMPTS):
        result = await client.set(
            lock_key,
            lock_token,
            ex=_LOCK_TTL_SECONDS,
            nx=True,
        )
        if result:
            return True
        if attempt < _LOCK_RETRY_ATTEMPTS - 1:
            await asyncio.sleep(_LOCK_RETRY_DELAY_SECONDS)
    return False


async def _release_lock(
    client: VisionSmoothingRedisClient,
    lock_key: str,
    lock_token: str,
) -> None:
    await client.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)


def _parse_observation_rows(raw_rows: list[str | bytes]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_row in raw_rows:
        if isinstance(raw_row, bytes):
            raw_row = raw_row.decode("utf-8")
        if not isinstance(raw_row, str):
            continue
        try:
            parsed = json.loads(raw_row)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _parse_optional_str(value: str | bytes | None) -> str | None:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value if isinstance(value, str) else None


def _log_cache_event(
    operation: str,
    outcome: str,
    **attributes: object,
) -> None:
    metric_attributes = {
        "operation": operation,
        "outcome": outcome,
        **{
            key: str(value)
            for key, value in attributes.items()
            if isinstance(value, str | int | float | bool)
        },
    }
    logger.info(
        "[Vision Smoothing Cache] %s %s",
        operation,
        outcome,
        extra=metric_attributes,
    )
    _emit_cache_metric(operation, outcome, **attributes)


def _emit_cache_metric(
    operation: str,
    outcome: str,
    **attributes: object,
) -> None:
    metric_attributes = {
        "operation": operation,
        "outcome": outcome,
        **{
            key: str(value)
            for key, value in attributes.items()
            if isinstance(value, str | int | float | bool)
        },
    }
    increment_counter(
        VISION_SMOOTHING_CACHE_OPERATION_METRIC,
        attributes=metric_attributes,
    )
