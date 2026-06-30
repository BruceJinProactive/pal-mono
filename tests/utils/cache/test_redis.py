import sys
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

import utils.cache.redis as redis_cache
from utils.cache.redis import (
    CacheAuthMode,
    RedisCacheSettings,
    build_redis_cache_client,
    close_redis_cache_client,
    get_redis_cache_client,
    get_redis_cache_password,
    get_redis_cache_settings,
)


def test_redis_cache_settings_defaults_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDIS_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("REDIS_CACHE_HOST", raising=False)

    settings = RedisCacheSettings()

    assert settings.enabled is False
    assert settings.host == ""
    assert settings.port == 6379
    assert settings.username == ""
    assert settings.secret_key == "REDIS_CACHE_AUTH_TOKEN"
    assert settings.auth_mode == CacheAuthMode.SECRETS_MANAGER
    assert settings.cluster_mode is False
    assert settings.ssl is True
    assert settings.default_ttl_seconds == 1800
    assert settings.socket_connect_timeout_seconds == 2.0
    assert settings.socket_timeout_seconds == 2.0
    assert settings.health_check_interval_seconds == 30


def test_redis_cache_settings_parse_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "cache.example.local")
    monkeypatch.setenv("REDIS_CACHE_PORT", "6380")
    monkeypatch.setenv("REDIS_CACHE_USERNAME", "shared-cache-user")
    monkeypatch.setenv("REDIS_CACHE_SECRET_KEY", "CUSTOM_CACHE_TOKEN")
    monkeypatch.setenv("REDIS_CACHE_AUTH_MODE", "secrets_manager")
    monkeypatch.setenv("REDIS_CACHE_CLUSTER_MODE", "true")
    monkeypatch.setenv("REDIS_CACHE_SSL", "false")
    monkeypatch.setenv("REDIS_CACHE_DEFAULT_TTL_SECONDS", "900")
    monkeypatch.setenv("REDIS_CACHE_SOCKET_CONNECT_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("REDIS_CACHE_SOCKET_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("REDIS_CACHE_HEALTH_CHECK_INTERVAL_SECONDS", "45")

    settings = RedisCacheSettings()

    assert settings.enabled is True
    assert settings.host == "cache.example.local"
    assert settings.port == 6380
    assert settings.username == "shared-cache-user"
    assert settings.secret_key == "CUSTOM_CACHE_TOKEN"
    assert settings.auth_mode == CacheAuthMode.SECRETS_MANAGER
    assert settings.cluster_mode is True
    assert settings.ssl is False
    assert settings.default_ttl_seconds == 900
    assert settings.socket_connect_timeout_seconds == 1.5
    assert settings.socket_timeout_seconds == 3.5
    assert settings.health_check_interval_seconds == 45


def test_redis_cache_settings_require_host_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "")

    with pytest.raises(ValidationError, match="REDIS_CACHE_HOST"):
        RedisCacheSettings()


def test_redis_cache_settings_require_secret_for_secrets_manager_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "cache.example.local")
    monkeypatch.setenv("REDIS_CACHE_AUTH_MODE", "secrets_manager")
    monkeypatch.setenv("REDIS_CACHE_SECRET_KEY", "")

    with pytest.raises(ValidationError, match="REDIS_CACHE_SECRET_KEY"):
        RedisCacheSettings()


def test_redis_cache_settings_iam_auth_allows_empty_secret_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "cache.example.local")
    monkeypatch.setenv("REDIS_CACHE_AUTH_MODE", "iam")
    monkeypatch.setenv("REDIS_CACHE_SECRET_KEY", "")

    settings = RedisCacheSettings()

    assert settings.auth_mode == CacheAuthMode.IAM
    assert settings.secret_key == ""


@pytest.mark.asyncio
async def test_redis_cache_client_disabled_returns_none() -> None:
    settings = RedisCacheSettings(enabled=False)

    assert await build_redis_cache_client(settings) is None


@pytest.mark.asyncio
async def test_redis_cache_client_iam_requires_token_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "cache.example.local")
    monkeypatch.setenv("REDIS_CACHE_AUTH_MODE", "iam")
    monkeypatch.setenv("REDIS_CACHE_SECRET_KEY", "")

    settings = RedisCacheSettings()

    with pytest.raises(NotImplementedError, match="IAM auth token provider"):
        await build_redis_cache_client(settings)


def test_get_redis_cache_settings_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_redis_cache_settings.cache_clear()
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "cache.example.local")

    settings = get_redis_cache_settings()

    assert settings.enabled is True
    assert settings.host == "cache.example.local"

    get_redis_cache_settings.cache_clear()


@pytest.mark.asyncio
async def test_redis_cache_password_disabled_returns_none() -> None:
    settings = RedisCacheSettings(enabled=False)

    assert await get_redis_cache_password(settings) is None


@pytest.mark.asyncio
async def test_redis_cache_password_iam_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_CACHE_ENABLED", "true")
    monkeypatch.setenv("REDIS_CACHE_HOST", "cache.example.local")
    monkeypatch.setenv("REDIS_CACHE_AUTH_MODE", "iam")
    monkeypatch.setenv("REDIS_CACHE_SECRET_KEY", "")

    settings = RedisCacheSettings()

    assert await get_redis_cache_password(settings) is None


@pytest.mark.asyncio
async def test_redis_cache_password_uses_secret_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_secret_lookup(secret_key: str) -> str:
        assert secret_key == "CUSTOM_CACHE_TOKEN"
        return "redis-password"

    import utils.secret

    monkeypatch.setattr(
        utils.secret,
        "async_get_client_secret_with_fallback",
        fake_secret_lookup,
    )
    settings = RedisCacheSettings(
        enabled=True,
        host="cache.example.local",
        secret_key="CUSTOM_CACHE_TOKEN",
    )

    assert await get_redis_cache_password(settings) == "redis-password"


@pytest.mark.asyncio
async def test_redis_cache_client_passes_connection_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeRedis:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

        async def aclose(self) -> None:
            return None

    redis_module = ModuleType("redis")
    setattr(redis_module, "__path__", [])
    redis_asyncio_module = ModuleType("redis.asyncio")
    setattr(redis_asyncio_module, "Redis", FakeRedis)
    setattr(redis_module, "asyncio", redis_asyncio_module)
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio_module)

    async def fake_password(_: RedisCacheSettings) -> str:
        return "redis-password"

    monkeypatch.setattr(
        redis_cache,
        "get_redis_cache_password",
        fake_password,
    )

    settings = RedisCacheSettings(
        enabled=True,
        host="cache.example.local",
        port=6380,
        username="shared-cache-user",
        ssl=True,
        socket_connect_timeout_seconds=1.5,
        socket_timeout_seconds=3.5,
        health_check_interval_seconds=45,
    )

    client = await build_redis_cache_client(settings)

    assert isinstance(client, FakeRedis)
    assert captured_kwargs == {
        "host": "cache.example.local",
        "port": 6380,
        "username": "shared-cache-user",
        "password": "redis-password",
        "ssl": True,
        "decode_responses": True,
        "socket_connect_timeout": 1.5,
        "socket_timeout": 3.5,
        "health_check_interval": 45,
    }


@pytest.mark.asyncio
async def test_redis_cache_client_uses_cluster_client_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeRedisCluster:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

        async def aclose(self) -> None:
            return None

    redis_module = ModuleType("redis")
    setattr(redis_module, "__path__", [])
    redis_asyncio_module = ModuleType("redis.asyncio")
    setattr(redis_asyncio_module, "__path__", [])
    redis_cluster_module = ModuleType("redis.asyncio.cluster")
    setattr(redis_cluster_module, "RedisCluster", FakeRedisCluster)
    setattr(redis_asyncio_module, "cluster", redis_cluster_module)
    setattr(redis_module, "asyncio", redis_asyncio_module)
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio.cluster", redis_cluster_module)

    async def fake_password(_: RedisCacheSettings) -> str:
        return "redis-password"

    monkeypatch.setattr(
        redis_cache,
        "get_redis_cache_password",
        fake_password,
    )

    settings = RedisCacheSettings(
        enabled=True,
        host="cluster-cache.example.local",
        port=6380,
        username="shared-cache-user",
        cluster_mode=True,
        ssl=True,
        socket_connect_timeout_seconds=1.5,
        socket_timeout_seconds=3.5,
        health_check_interval_seconds=45,
    )

    client = await build_redis_cache_client(settings)

    assert isinstance(client, FakeRedisCluster)
    assert captured_kwargs == {
        "host": "cluster-cache.example.local",
        "port": 6380,
        "username": "shared-cache-user",
        "password": "redis-password",
        "ssl": True,
        "decode_responses": True,
        "socket_connect_timeout": 1.5,
        "socket_timeout": 3.5,
        "health_check_interval": 45,
    }


@pytest.mark.asyncio
async def test_get_redis_cache_client_builds_once_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await close_redis_cache_client()
    build_count = 0
    fake_client = _FakeRedisClient()

    async def fake_build_client() -> _FakeRedisClient:
        nonlocal build_count
        build_count += 1
        await redis_cache.asyncio.sleep(0)
        return fake_client

    monkeypatch.setattr(
        redis_cache,
        "build_redis_cache_client",
        fake_build_client,
    )

    first_client, second_client = await redis_cache.asyncio.gather(
        get_redis_cache_client(),
        get_redis_cache_client(),
    )

    assert first_client is fake_client
    assert second_client is fake_client
    assert build_count == 1

    third_client = await get_redis_cache_client()

    assert third_client is fake_client
    assert build_count == 1

    await close_redis_cache_client()


@pytest.mark.asyncio
async def test_close_redis_cache_client_without_client() -> None:
    await close_redis_cache_client()

    assert redis_cache._redis_cache_client is None
    assert redis_cache._redis_cache_client_initialized is False


@pytest.mark.asyncio
async def test_close_redis_cache_client_closes_existing_client() -> None:
    fake_client = _FakeRedisClient()
    redis_cache._redis_cache_client = fake_client
    redis_cache._redis_cache_client_initialized = True

    await close_redis_cache_client()

    assert fake_client.closed is True
    assert redis_cache._redis_cache_client is None
    assert redis_cache._redis_cache_client_initialized is False


class _FakeRedisClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True
