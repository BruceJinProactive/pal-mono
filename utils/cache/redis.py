from __future__ import annotations

import asyncio
from enum import StrEnum
from functools import lru_cache
from typing import Protocol, Self, cast

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisClient(Protocol):
    async def aclose(self) -> None: ...


_redis_cache_client: RedisClient | None = None
_redis_cache_client_initialized = False
_redis_cache_client_lock = asyncio.Lock()


class CacheAuthMode(StrEnum):
    SECRETS_MANAGER = "secrets_manager"
    IAM = "iam"


class RedisCacheSettings(BaseSettings):
    """Environment-backed settings for the shared Redis/Valkey cache."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_CACHE_",
        extra="ignore",
    )

    enabled: bool = False
    host: str = ""
    port: int = Field(default=6379, ge=1, le=65535)
    username: str = ""
    secret_key: str = "REDIS_CACHE_AUTH_TOKEN"  # noqa: S105
    auth_mode: CacheAuthMode = CacheAuthMode.SECRETS_MANAGER
    cluster_mode: bool = False
    ssl: bool = True
    default_ttl_seconds: int = Field(default=1800, ge=1)
    socket_connect_timeout_seconds: float = Field(default=2.0, gt=0)
    socket_timeout_seconds: float = Field(default=2.0, gt=0)
    health_check_interval_seconds: int = Field(default=30, ge=0)

    @model_validator(mode="after")
    def validate_enabled_settings(self) -> Self:
        """Require connection details only when the shared cache is enabled."""
        if not self.enabled:
            return self

        if not self.host:
            raise ValueError("REDIS_CACHE_HOST is required when enabled")

        if self.auth_mode == CacheAuthMode.SECRETS_MANAGER and not self.secret_key:
            raise ValueError(
                "REDIS_CACHE_SECRET_KEY is required for secrets_manager auth"
            )

        return self


@lru_cache(maxsize=1)
def get_redis_cache_settings() -> RedisCacheSettings:
    return RedisCacheSettings()


async def get_redis_cache_password(
    settings: RedisCacheSettings | None = None,
) -> str | None:
    settings = settings or get_redis_cache_settings()

    if not settings.enabled or settings.auth_mode == CacheAuthMode.IAM:
        return None

    from utils.secret import async_get_client_secret_with_fallback

    return await async_get_client_secret_with_fallback(settings.secret_key)


async def build_redis_cache_client(
    settings: RedisCacheSettings | None = None,
) -> RedisClient | None:
    settings = settings or get_redis_cache_settings()

    if not settings.enabled:
        return None

    if settings.auth_mode == CacheAuthMode.IAM:
        raise NotImplementedError(
            "REDIS_CACHE_AUTH_MODE=iam requires an IAM auth token provider"
        )

    password = await get_redis_cache_password(settings)

    if settings.cluster_mode:
        from redis.asyncio.cluster import RedisCluster

        return cast(
            RedisClient,
            RedisCluster(
                host=settings.host,
                port=settings.port,
                username=settings.username or None,
                password=password,
                ssl=settings.ssl,
                decode_responses=True,
                socket_connect_timeout=settings.socket_connect_timeout_seconds,
                socket_timeout=settings.socket_timeout_seconds,
                health_check_interval=settings.health_check_interval_seconds,
            ),
        )

    from redis.asyncio import Redis

    return cast(
        RedisClient,
        Redis(
            host=settings.host,
            port=settings.port,
            username=settings.username or None,
            password=password,
            ssl=settings.ssl,
            decode_responses=True,
            socket_connect_timeout=settings.socket_connect_timeout_seconds,
            socket_timeout=settings.socket_timeout_seconds,
            health_check_interval=settings.health_check_interval_seconds,
        ),
    )


async def get_redis_cache_client() -> RedisClient | None:
    global _redis_cache_client, _redis_cache_client_initialized

    if _redis_cache_client_initialized:
        return _redis_cache_client

    async with _redis_cache_client_lock:
        if not _redis_cache_client_initialized:
            _redis_cache_client = await build_redis_cache_client()
            _redis_cache_client_initialized = True

    return _redis_cache_client


async def close_redis_cache_client() -> None:
    global _redis_cache_client, _redis_cache_client_initialized

    if _redis_cache_client is None:
        _redis_cache_client_initialized = False
        return

    await _redis_cache_client.aclose()
    _redis_cache_client = None
    _redis_cache_client_initialized = False
