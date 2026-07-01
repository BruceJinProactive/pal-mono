from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from typing import Any

from langfuse import Langfuse, propagate_attributes
from opentelemetry import context as otel_context

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

_DEFAULT_LANGFUSE_HOST = "https://us.cloud.langfuse.com"
_vision_langfuse_client: Langfuse | None = None


def _get_vision_langfuse_client() -> Langfuse | None:
    global _vision_langfuse_client

    if _vision_langfuse_client is not None:
        return _vision_langfuse_client

    try:
        public_key = get_server_secret_with_fallback("LANGFUSE_VISION_PUBLIC_KEY")
        secret_key = get_server_secret_with_fallback("LANGFUSE_VISION_SECRET_KEY")
    except Exception:
        logger.warning(
            "[Vision Observation] Langfuse vision credentials unavailable; "
            "skipping Langfuse trace",
            exc_info=True,
        )
        return None

    host = (
        os.getenv("LANGFUSE_VISION_HOST")
        or os.getenv("LANGFUSE_HOST")
        or _DEFAULT_LANGFUSE_HOST
    )
    try:
        _vision_langfuse_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=host,
        )
    except Exception:
        logger.warning(
            "[Vision Observation] Failed to initialize Langfuse vision client; "
            "skipping Langfuse trace",
            exc_info=True,
        )
        return None
    return _vision_langfuse_client


def _string_metadata(value: object) -> str:
    text = str(value)
    return text[:200]


def _usage_details(token_usage: dict[str, Any]) -> dict[str, int] | None:
    usage: dict[str, int] = {}
    for source_key, target_key in (
        ("prompt_tokens", "input"),
        ("input_tokens", "input"),
        ("completion_tokens", "output"),
        ("output_tokens", "output"),
        ("total_tokens", "total"),
    ):
        value = token_usage.get(source_key)
        if isinstance(value, int):
            usage[target_key] = value
    return usage or None


def _model_usage(token_usage: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = token_usage.get("prompt_tokens")
    if prompt_tokens is None:
        prompt_tokens = token_usage.get("input_tokens")

    completion_tokens = token_usage.get("completion_tokens")
    if completion_tokens is None:
        completion_tokens = token_usage.get("output_tokens")

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": token_usage.get("total_tokens"),
    }


@contextmanager
def langfuse_vision_observation_span(
    *,
    camera_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    account_name: str,
    project_name: str,
    llm_provider: str,
    llm_model: str,
    is_test: bool,
    input_payload: dict[str, Any],
) -> Generator[Any | None, None, None]:
    lf = _get_vision_langfuse_client()
    if lf is None:
        yield None
        return

    otel_token = otel_context.attach(otel_context.Context())
    stack = ExitStack()
    try:
        observation = stack.enter_context(
            lf.start_as_current_observation(
                name="Pal Vision Observation LLM",
                as_type="span",
                input=input_payload,
                metadata={
                    "camera_id": str(camera_id),
                    "camera_config_id": str(camera_config_id),
                    "account_name": account_name,
                    "project_name": project_name,
                    "llm_provider": llm_provider,
                    "media_type": "image",
                    "is_test": str(is_test).lower(),
                },
            )
        )
        stack.enter_context(
            propagate_attributes(
                trace_name="Pal Vision Observation",
                session_id=str(camera_config_id),
                tags=[
                    "product:pal-vision",
                    "media_type:image",
                    f"account:{account_name}",
                    f"provider:{llm_provider}",
                    f"model:{llm_model}",
                    f"is_test:{str(is_test).lower()}",
                ],
                metadata={
                    "camera_id": str(camera_id),
                    "camera_config_id": str(camera_config_id),
                    "account_name": _string_metadata(account_name),
                    "project_name": _string_metadata(project_name),
                    "llm_provider": _string_metadata(llm_provider),
                    "llm_model": _string_metadata(llm_model),
                },
            )
        )
    except Exception:
        stack.close()
        otel_context.detach(otel_token)
        logger.warning(
            "[Vision Observation] Failed to start Langfuse vision trace",
            extra={
                "camera_id": str(camera_id),
                "camera_config_id": str(camera_config_id),
            },
            exc_info=True,
        )
        yield None
        return

    try:
        yield observation
    finally:
        try:
            stack.close()
        finally:
            otel_context.detach(otel_token)


def update_langfuse_vision_observation(
    observation: Any | None,
    *,
    output: dict[str, Any],
    token_usage: dict[str, Any],
) -> None:
    if observation is None:
        return

    try:
        observation.update(
            output=output,
            metadata={"model_usage": _model_usage(token_usage)},
            usage_details=_usage_details(token_usage),
        )
    except Exception:
        logger.warning(
            "[Vision Observation] Failed to update Langfuse vision trace",
            exc_info=True,
        )
