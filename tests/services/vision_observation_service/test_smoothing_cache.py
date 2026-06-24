from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import services.vision_observation_service._smoothing_cache as smoothing_cache
from services.vision_observation_service._smoothing import (
    EventGenerationConfig,
    SmoothingObservation,
    parse_event_generation_config,
)
from services.vision_observation_service._smoothing_cache import (
    acquire_smoothing_cache_buffer,
    build_finalized_key,
    build_lock_key,
    build_observations_key,
)
from utils.cache.redis import RedisCacheSettings


def _config(window_frames: int = 5) -> EventGenerationConfig:
    return parse_event_generation_config(
        {
            "strategy": "centered_majority_vote",
            "window_frames": window_frames,
            "frame_interval_seconds": 15,
            "max_frame_gap_seconds": 3600,
        }
    )


def _observation(
    observed_at: datetime,
    state_id: uuid.UUID,
    state: str,
    frame_s3_key: str,
    camera_config_id: uuid.UUID | None = None,
) -> SmoothingObservation:
    return SmoothingObservation(
        observed_at=observed_at,
        state_id=state_id,
        state=state,
        confidence=0.9,
        frame_s3_key=frame_s3_key,
        camera_config_id=camera_config_id or uuid.uuid4(),
    )


def _install_cache_fakes(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: "_FakeRedisClient | None",
    metrics: list[tuple[str, dict[str, str]]] | None = None,
    settings: RedisCacheSettings | None = None,
) -> None:
    async def fake_get_client() -> _FakeRedisClient | None:
        return fake_client

    def fake_get_settings() -> RedisCacheSettings:
        return settings or RedisCacheSettings(
            enabled=True,
            host="cache.example.local",
            default_ttl_seconds=1800,
        )

    def fake_increment_counter(name: str, attributes: dict[str, str]) -> None:
        if metrics is not None:
            metrics.append((name, attributes))

    monkeypatch.setattr(
        smoothing_cache,
        "get_vision_smoothing_cache_client",
        fake_get_client,
    )
    monkeypatch.setattr(smoothing_cache, "get_redis_cache_settings", fake_get_settings)
    monkeypatch.setattr(smoothing_cache, "increment_counter", fake_increment_counter)


def _hash_tag(key: str) -> str:
    start = key.index("{")
    end = key.index("}", start)
    return key[start : end + 1]


def test_smoothing_cache_keys_share_cluster_hash_tag() -> None:
    entity_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    definition_type = "cleanliness"

    observations_key = build_observations_key(
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

    assert (
        _hash_tag(observations_key) == _hash_tag(finalized_key) == _hash_tag(lock_key)
    )
    assert observations_key.endswith(":observations")
    assert finalized_key.endswith(":finalized")
    assert lock_key.endswith(":lock")


@pytest.mark.asyncio
async def test_cache_buffer_appends_dedupes_trims_and_applies_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    definition_type = "cleanliness"
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    fake_client = _FakeRedisClient()
    _install_cache_fakes(monkeypatch, fake_client)
    config = _config(window_frames=3)

    for index in range(10):
        state_id = dirty_id if index != 9 else clean_id
        buffer = await acquire_smoothing_cache_buffer(
            entity_id,
            camera_config_id,
            definition_type,
            _observation(
                start + timedelta(seconds=index * 15),
                state_id,
                "dirty" if state_id == dirty_id else "clean",
                f"frame-{index}.jpg",
                camera_config_id=camera_config_id,
            ),
            config,
        )
        assert buffer is not None
        await buffer.save()
        await buffer.release()

    replacement = await acquire_smoothing_cache_buffer(
        entity_id,
        camera_config_id,
        definition_type,
        _observation(
            start + timedelta(seconds=9 * 15),
            dirty_id,
            "dirty",
            "frame-9.jpg",
            camera_config_id=camera_config_id,
        ),
        config,
    )
    assert replacement is not None
    await replacement.save()
    await replacement.release()

    observations_key = build_observations_key(
        entity_id,
        camera_config_id,
        definition_type,
    )
    rows = [json.loads(raw) for raw in fake_client.store[observations_key]]
    assert len(rows) == 7
    assert rows[-1]["observed_at"] == "2026-06-19T09:02:15+00:00"
    assert rows[-1]["state"] == "dirty"
    assert fake_client.expire_calls[-1] == (observations_key, 7200)


@pytest.mark.asyncio
async def test_cache_buffer_reads_and_writes_finalized_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    definition_type = "cleanliness"
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    fake_client = _FakeRedisClient()
    _install_cache_fakes(monkeypatch, fake_client)
    config = _config(window_frames=3)

    for index, state_id in enumerate([dirty_id, clean_id, dirty_id]):
        buffer = await acquire_smoothing_cache_buffer(
            entity_id,
            camera_config_id,
            definition_type,
            _observation(
                start + timedelta(seconds=index * 15),
                state_id,
                "dirty" if state_id == dirty_id else "clean",
                f"frame-{index}.jpg",
                camera_config_id=camera_config_id,
            ),
            config,
        )
        assert buffer is not None
        decisions = buffer.collect_ready_decisions(start + timedelta(seconds=45))
        for decision in decisions:
            buffer.mark_finalized(decision.center_observed_at)
        await buffer.save()
        await buffer.release()

    finalized_key = build_finalized_key(
        entity_id,
        camera_config_id,
        definition_type,
    )
    assert fake_client.values[finalized_key] == "2026-06-19T09:00:15+00:00"

    next_buffer = await acquire_smoothing_cache_buffer(
        entity_id,
        camera_config_id,
        definition_type,
        _observation(
            start + timedelta(seconds=45),
            dirty_id,
            "dirty",
            "frame-3.jpg",
            camera_config_id=camera_config_id,
        ),
        config,
    )
    assert next_buffer is not None
    next_decisions = next_buffer.collect_ready_decisions(start + timedelta(seconds=60))
    assert [decision.center_observed_at for decision in next_decisions] == [
        start + timedelta(seconds=30)
    ]
    await next_buffer.save()
    await next_buffer.release()


@pytest.mark.asyncio
async def test_cache_buffer_skips_when_redis_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, None, metrics=metrics)
    camera_config_id = uuid.uuid4()

    buffer = await acquire_smoothing_cache_buffer(
        uuid.uuid4(),
        camera_config_id,
        "cleanliness",
        _observation(
            datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc),
            uuid.uuid4(),
            "dirty",
            "frame.jpg",
            camera_config_id=camera_config_id,
        ),
        _config(),
    )

    assert buffer is None
    assert metrics[-1] == (
        "vision_smoothing_cache.operation",
        {"operation": "acquire", "outcome": "skipped", "reason": "disabled"},
    )


@pytest.mark.asyncio
async def test_cache_buffer_skips_when_lock_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    definition_type = "cleanliness"
    fake_client = _FakeRedisClient()
    fake_client.values[build_lock_key(entity_id, camera_config_id, definition_type)] = (
        "other-lock"
    )
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    buffer = await acquire_smoothing_cache_buffer(
        entity_id,
        camera_config_id,
        definition_type,
        _observation(
            datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc),
            uuid.uuid4(),
            "dirty",
            "frame.jpg",
            camera_config_id=camera_config_id,
        ),
        _config(),
    )

    assert buffer is None
    assert metrics[-1] == (
        "vision_smoothing_cache.operation",
        {
            "operation": "acquire",
            "outcome": "skipped",
            "reason": "lock_unavailable",
        },
    )


@pytest.mark.asyncio
async def test_cache_buffer_skips_when_camera_id_mismatches_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient()
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)

    buffer = await acquire_smoothing_cache_buffer(
        uuid.uuid4(),
        uuid.uuid4(),
        "cleanliness",
        _observation(
            datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc),
            uuid.uuid4(),
            "dirty",
            "frame.jpg",
            camera_config_id=uuid.uuid4(),
        ),
        _config(),
    )

    assert buffer is None
    assert fake_client.store == {}
    assert fake_client.values == {}
    assert metrics[-1] == (
        "vision_smoothing_cache.operation",
        {"operation": "acquire", "outcome": "error"},
    )


@pytest.mark.asyncio
async def test_cache_buffer_skips_on_redis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeRedisClient(raise_on_lrange=True)
    metrics: list[tuple[str, dict[str, str]]] = []
    _install_cache_fakes(monkeypatch, fake_client, metrics=metrics)
    camera_config_id = uuid.uuid4()

    buffer = await acquire_smoothing_cache_buffer(
        uuid.uuid4(),
        camera_config_id,
        "cleanliness",
        _observation(
            datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc),
            uuid.uuid4(),
            "dirty",
            "frame.jpg",
            camera_config_id=camera_config_id,
        ),
        _config(),
    )

    assert buffer is None
    assert metrics[-1] == (
        "vision_smoothing_cache.operation",
        {"operation": "acquire", "outcome": "error"},
    )


class _FakeRedisClient:
    def __init__(self, raise_on_lrange: bool = False) -> None:
        self.store: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []
        self.raise_on_lrange = raise_on_lrange

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        if self.raise_on_lrange:
            raise RuntimeError("lrange failed")
        rows = self.store.get(name, [])
        if end == -1:
            return rows[start:]
        return rows[start : end + 1]

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        if nx and name in self.values:
            return False
        self.values[name] = value
        if ex is not None:
            self.expire_calls.append((name, ex))
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int:
        del script, numkeys
        key, token = keys_and_args
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self, transaction)


class _FakePipeline:
    def __init__(self, client: _FakeRedisClient, transaction: bool) -> None:
        self.client = client
        self.transaction = transaction
        self.commands: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> bool | None:
        return None

    def delete(self, *names: str) -> object:
        self.commands.append(("delete", names))
        return None

    def rpush(self, name: str, *values: str) -> object:
        self.commands.append(("rpush", (name, *values)))
        return None

    def set(self, name: str, value: str) -> object:
        self.commands.append(("set", (name, value)))
        return None

    def expire(self, name: str, time: int) -> object:
        self.commands.append(("expire", (name, time)))
        return None

    async def execute(self) -> object:
        for command, args in self.commands:
            if command == "delete":
                for name in args:
                    self.client.store.pop(name, None)
                    self.client.values.pop(name, None)
            elif command == "rpush":
                name = args[0]
                values = [str(value) for value in args[1:]]
                self.client.store.setdefault(str(name), []).extend(values)
            elif command == "set":
                name, value = args
                self.client.values[str(name)] = str(value)
            elif command == "expire":
                name, time = args
                self.client.expire_calls.append((str(name), int(time)))
        return None
