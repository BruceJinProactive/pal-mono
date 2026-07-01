from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from services.vision_observation_service import _implementation, _tracing


class _FakeObservation:
    def __init__(self) -> None:
        self.update_calls: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.update_calls.append(kwargs)


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.observation = _FakeObservation()
        self.start_kwargs: dict[str, Any] | None = None

    @contextmanager
    def start_as_current_observation(
        self, **kwargs: Any
    ) -> Generator[_FakeObservation, None, None]:
        self.start_kwargs = kwargs
        yield self.observation


def _reset_vision_langfuse_client() -> None:
    _tracing._vision_langfuse_client = None


def test_vision_langfuse_client_uses_vision_project_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[dict[str, str | None]] = []

    def fake_get_secret(key: str) -> str:
        return {
            "LANGFUSE_VISION_PUBLIC_KEY": "vision-public",
            "LANGFUSE_VISION_SECRET_KEY": "vision-secret",
        }[key]

    class FakeLangfuse:
        def __init__(
            self,
            *,
            public_key: str,
            secret_key: str,
            base_url: str,
        ) -> None:
            created_clients.append(
                {
                    "public_key": public_key,
                    "secret_key": secret_key,
                    "base_url": base_url,
                }
            )

    monkeypatch.setattr(_tracing, "get_server_secret_with_fallback", fake_get_secret)
    monkeypatch.setattr(_tracing, "Langfuse", FakeLangfuse)
    monkeypatch.setenv("LANGFUSE_VISION_HOST", "https://vision.langfuse.local")
    _reset_vision_langfuse_client()

    try:
        client = _tracing._get_vision_langfuse_client()
    finally:
        _reset_vision_langfuse_client()

    assert client is not None
    assert created_clients == [
        {
            "public_key": "vision-public",
            "secret_key": "vision-secret",
            "base_url": "https://vision.langfuse.local",
        }
    ]


def test_vision_langfuse_client_retries_after_secret_lookup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[dict[str, str | None]] = []
    failed_once = False

    def fake_get_secret(key: str) -> str:
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise RuntimeError("temporary secret lookup failure")
        return {
            "LANGFUSE_VISION_PUBLIC_KEY": "vision-public",
            "LANGFUSE_VISION_SECRET_KEY": "vision-secret",
        }[key]

    class FakeLangfuse:
        def __init__(
            self,
            *,
            public_key: str,
            secret_key: str,
            base_url: str,
        ) -> None:
            created_clients.append(
                {
                    "public_key": public_key,
                    "secret_key": secret_key,
                    "base_url": base_url,
                }
            )

    monkeypatch.setattr(_tracing, "get_server_secret_with_fallback", fake_get_secret)
    monkeypatch.setattr(_tracing, "Langfuse", FakeLangfuse)
    monkeypatch.setenv("LANGFUSE_VISION_HOST", "https://vision.langfuse.local")
    _reset_vision_langfuse_client()

    try:
        assert _tracing._get_vision_langfuse_client() is None
        client = _tracing._get_vision_langfuse_client()
    finally:
        _reset_vision_langfuse_client()

    assert client is not None
    assert created_clients == [
        {
            "public_key": "vision-public",
            "secret_key": "vision-secret",
            "base_url": "https://vision.langfuse.local",
        }
    ]


def test_vision_langfuse_client_retries_after_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[dict[str, str | None]] = []
    failed_once = False

    def fake_get_secret(key: str) -> str:
        return {
            "LANGFUSE_VISION_PUBLIC_KEY": "vision-public",
            "LANGFUSE_VISION_SECRET_KEY": "vision-secret",
        }[key]

    class FakeLangfuse:
        def __init__(
            self,
            *,
            public_key: str,
            secret_key: str,
            base_url: str,
        ) -> None:
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise RuntimeError("temporary Langfuse config failure")
            created_clients.append(
                {
                    "public_key": public_key,
                    "secret_key": secret_key,
                    "base_url": base_url,
                }
            )

    monkeypatch.setattr(_tracing, "get_server_secret_with_fallback", fake_get_secret)
    monkeypatch.setattr(_tracing, "Langfuse", FakeLangfuse)
    monkeypatch.setenv("LANGFUSE_VISION_HOST", "https://vision.langfuse.local")
    _reset_vision_langfuse_client()

    try:
        assert _tracing._get_vision_langfuse_client() is None
        client = _tracing._get_vision_langfuse_client()
    finally:
        _reset_vision_langfuse_client()

    assert client is not None
    assert created_clients == [
        {
            "public_key": "vision-public",
            "secret_key": "vision-secret",
            "base_url": "https://vision.langfuse.local",
        }
    ]


def test_langfuse_vision_observation_span_sets_trace_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeLangfuseClient()
    propagated: dict[str, Any] = {}

    @contextmanager
    def fake_propagate_attributes(**kwargs: Any) -> Generator[None, None, None]:
        propagated.update(kwargs)
        yield

    monkeypatch.setattr(_tracing, "_get_vision_langfuse_client", lambda: fake_client)
    monkeypatch.setattr(_tracing, "propagate_attributes", fake_propagate_attributes)

    camera_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    input_payload = {"analysis_task": "count trays"}

    with _tracing.langfuse_vision_observation_span(
        camera_id=camera_id,
        camera_config_id=camera_config_id,
        account_name="pokeworks",
        project_name="sf-store",
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        is_test=False,
        input_payload=input_payload,
    ) as observation:
        assert observation is fake_client.observation

    assert fake_client.start_kwargs == {
        "name": "Pal Vision Observation LLM",
        "as_type": "span",
        "input": input_payload,
        "metadata": {
            "camera_id": str(camera_id),
            "camera_config_id": str(camera_config_id),
            "account_name": "pokeworks",
            "project_name": "sf-store",
            "llm_provider": "google",
            "media_type": "image",
            "is_test": "false",
        },
    }
    assert propagated["trace_name"] == "Pal Vision Observation"
    assert propagated["session_id"] == str(camera_config_id)
    assert "product:pal-vision" in propagated["tags"]
    assert "account:pokeworks" in propagated["tags"]
    assert "model:gemini-2.5-flash" in propagated["tags"]
    assert propagated["metadata"]["account_name"] == "pokeworks"
    assert propagated["metadata"]["project_name"] == "sf-store"


@pytest.mark.asyncio
async def test_project_trace_names_include_account_and_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.uuid4()
    project = SimpleNamespace(
        name="sf-store",
        account=SimpleNamespace(name="pokeworks"),
    )

    class FakeProjectRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def get_project(self, project_id_arg: uuid.UUID) -> object:
            assert project_id_arg == project_id
            return project

    monkeypatch.setattr(
        _implementation,
        "ProjectRepositoryAsync",
        FakeProjectRepository,
    )

    account_name, project_name = await _implementation._get_project_trace_names(
        AsyncMock(),
        project_id,
    )

    assert account_name == "pokeworks"
    assert project_name == "sf-store"


@pytest.mark.asyncio
async def test_project_trace_names_rolls_back_after_lookup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.uuid4()
    session = AsyncMock()

    class FakeProjectRepository:
        def __init__(self, session_arg: object) -> None:
            self.session = session_arg

        async def get_project(self, project_id_arg: uuid.UUID) -> object:
            assert project_id_arg == project_id
            raise SQLAlchemyError("database connection dropped")

    monkeypatch.setattr(
        _implementation,
        "ProjectRepositoryAsync",
        FakeProjectRepository,
    )

    account_name, project_name = await _implementation._get_project_trace_names(
        session,
        project_id,
    )

    assert (account_name, project_name) == ("unknown", "unknown")
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_project_trace_names_does_not_swallow_unexpected_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid.uuid4()
    session = AsyncMock()

    class FakeProjectRepository:
        def __init__(self, session_arg: object) -> None:
            self.session = session_arg

        async def get_project(self, project_id_arg: uuid.UUID) -> object:
            assert project_id_arg == project_id
            raise RuntimeError("unexpected project repository failure")

    monkeypatch.setattr(
        _implementation,
        "ProjectRepositoryAsync",
        FakeProjectRepository,
    )

    with pytest.raises(RuntimeError, match="unexpected project repository failure"):
        await _implementation._get_project_trace_names(
            session,
            project_id,
        )

    session.rollback.assert_not_awaited()


def test_update_langfuse_vision_observation_records_model_usage() -> None:
    observation = _FakeObservation()

    _tracing.update_langfuse_vision_observation(
        observation,
        output={"image_relevant": True},
        token_usage={
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    )

    assert observation.update_calls == [
        {
            "output": {"image_relevant": True},
            "metadata": {
                "model_usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                }
            },
            "usage_details": {
                "input": 11,
                "output": 7,
                "total": 18,
            },
        }
    ]


def test_update_langfuse_vision_observation_preserves_zero_token_usage() -> None:
    observation = _FakeObservation()

    _tracing.update_langfuse_vision_observation(
        observation,
        output={"image_relevant": True},
        token_usage={
            "prompt_tokens": 0,
            "input_tokens": 11,
            "completion_tokens": 0,
            "output_tokens": 7,
            "total_tokens": 0,
        },
    )

    assert observation.update_calls[0]["metadata"] == {
        "model_usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    }
