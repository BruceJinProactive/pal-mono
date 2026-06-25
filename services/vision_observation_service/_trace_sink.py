from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from typing import Any

from services.asset_service._utils import AWS_ASSET_BUCKET_NAME
from utils.log import logger, request_id_ctx

_TRACE_PREFIX = "debug/vision_inference_traces"
_TRACE_SAMPLE_RATE = 0.005
_IMAGE_BODY_KEYS = {
    "base64",
    "base64_data",
    "image_base64",
    "image_body",
    "image_bytes",
    "body",
}


@dataclass(frozen=True)
class VisionInferenceTraceResult:
    trace_id: str
    trace_s3_key: str
    raw_frame_s3_key: str
    llm_input_frame_s3_key: str


_background_trace_tasks: set[asyncio.Task[VisionInferenceTraceResult | None]] = set()


def runtime_env() -> str:
    return (os.getenv("RUNTIME_ENV") or "dev").strip().lower() or "dev"


def build_sha() -> str | None:
    for env_name in (
        "BUILD_SHA",
        "GIT_SHA",
        "COMMIT_SHA",
        "CODEBUILD_RESOLVED_SOURCE_VERSION",
        "SENTRY_RELEASE",
        "RELEASE_TAG",
    ):
        value = os.getenv(env_name)
        if value:
            return value.strip()
    return None


def should_write_vision_inference_trace(_camera_config_id: uuid.UUID) -> bool:
    return random.random() < _TRACE_SAMPLE_RATE


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_partition_value(value: object) -> str:
    text = str(value)
    return "".join(
        char if char.isalnum() or char in {"-", "_", ".", "="} else "_" for char in text
    )


def _trace_id_from_request_id(request_id: str | None) -> str:
    if request_id:
        trace_id = "".join(
            char for char in request_id.strip() if char.isalnum() or char in {"-", "_"}
        )
        if trace_id:
            return trace_id[:128]
    return str(uuid.uuid4())


def _trace_base_key(
    *,
    env: str,
    observed_at: datetime,
    camera_config_id: uuid.UUID,
    trace_id: str,
) -> str:
    observed_at_utc = _utc_datetime(observed_at)
    return (
        f"{_TRACE_PREFIX}/"
        f"env={_safe_partition_value(env)}/"
        f"dt={observed_at_utc:%Y-%m-%d}/"
        f"hour={observed_at_utc:%H}/"
        f"camera_config_id={camera_config_id}/"
        f"trace_id={_safe_partition_value(trace_id)}"
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes omitted>"
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return str(value)


def _scrub_image_bodies(value: Any) -> Any:
    if isinstance(value, Mapping):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower in _IMAGE_BODY_KEYS or key_lower.endswith("_base64"):
                continue
            scrubbed[key_text] = _scrub_image_bodies(item)
        return scrubbed
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_scrub_image_bodies(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return "<data image omitted>"
    return _jsonable(value)


async def _put_object(
    s3_client: Any,
    key: str,
    body: bytes,
    content_type: str,
    metadata: dict[str, str],
) -> None:
    await asyncio.to_thread(
        s3_client.put_object,
        Bucket=AWS_ASSET_BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType=content_type,
        Metadata=metadata,
    )


async def maybe_write_vision_inference_trace(
    *,
    s3_client: Any,
    camera_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    image_url: str | None,
    observed_at: datetime,
    llm_provider: str,
    llm_model: str,
    system_prompt: str,
    llm_prompt: str,
    structured_output_schema: dict[str, Any],
    entities_with_states: list[dict[str, Any]],
    reference_image_metadata: list[Any],
    raw_llm_response: dict[str, Any],
    entity_observations: list[Any],
    token_usage: dict[str, Any],
    image_relevant: bool,
    raw_frame_bytes: bytes,
    llm_input_frame_bytes: bytes,
) -> VisionInferenceTraceResult | None:
    if not should_write_vision_inference_trace(camera_config_id):
        return None

    request_id = request_id_ctx.get() or None
    trace_id = _trace_id_from_request_id(request_id)
    env = runtime_env()
    base_key = _trace_base_key(
        env=env,
        observed_at=observed_at,
        camera_config_id=camera_config_id,
        trace_id=trace_id,
    )
    raw_frame_key = f"{base_key}/raw_frame.jpg"
    llm_input_frame_key = f"{base_key}/llm_input_frame.jpg"
    trace_key = f"{base_key}/trace.json"
    metadata = {
        "trace_id": trace_id,
        "env": env,
        "camera_config_id": str(camera_config_id),
    }

    trace_payload = {
        "trace_id": trace_id,
        "env": env,
        "request_id": request_id,
        "camera_id": str(camera_id),
        "camera_config_id": str(camera_config_id),
        "source_image_url": image_url,
        "frame_s3_key": image_url,
        "observed_at": _utc_datetime(observed_at).isoformat(),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "system_prompt": system_prompt,
        "analysis_task": llm_prompt,
        "llm_prompt": llm_prompt,
        "structured_output_schema": _jsonable(structured_output_schema),
        "entity_roi_hints": [
            {
                "entity_name": entity.get("name"),
                "roi_hint": _jsonable(entity.get("roi_hint")),
            }
            for entity in entities_with_states
        ],
        "reference_images": _scrub_image_bodies(reference_image_metadata),
        "artifacts": {
            "raw_frame_s3_key": raw_frame_key,
            "llm_input_frame_s3_key": llm_input_frame_key,
            "trace_s3_key": trace_key,
        },
        "raw_llm_response": _jsonable(raw_llm_response),
        "entity_observations": _jsonable(entity_observations),
        "token_usage": _jsonable(token_usage),
        "image_relevant": image_relevant,
        "build_sha": build_sha(),
    }
    trace_json = json.dumps(
        trace_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    try:
        await _put_object(
            s3_client, raw_frame_key, raw_frame_bytes, "image/jpeg", metadata
        )
        await _put_object(
            s3_client,
            llm_input_frame_key,
            llm_input_frame_bytes,
            "image/jpeg",
            metadata,
        )
        await _put_object(
            s3_client, trace_key, trace_json, "application/json", metadata
        )
    except Exception:
        logger.warning(
            "[Vision Observation Trace] Failed to write inference trace",
            extra={
                "trace_id": trace_id,
                "camera_id": str(camera_id),
                "camera_config_id": str(camera_config_id),
                "trace_s3_key": trace_key,
            },
            exc_info=True,
        )
        return None

    return VisionInferenceTraceResult(
        trace_id=trace_id,
        trace_s3_key=trace_key,
        raw_frame_s3_key=raw_frame_key,
        llm_input_frame_s3_key=llm_input_frame_key,
    )


def _log_background_trace_failure(
    task: asyncio.Future[Any],
) -> None:
    if task.cancelled():
        return

    exception = task.exception()
    if exception is None:
        return

    logger.warning(
        "[Vision Observation Trace] Background inference trace task failed",
        exc_info=(type(exception), exception, exception.__traceback__),
    )


def schedule_vision_inference_trace(
    *,
    s3_client: Any,
    camera_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    image_url: str | None,
    observed_at: datetime,
    llm_provider: str,
    llm_model: str,
    system_prompt: str,
    llm_prompt: str,
    structured_output_schema: dict[str, Any],
    entities_with_states: list[dict[str, Any]],
    reference_image_metadata: list[Any],
    raw_llm_response: dict[str, Any],
    entity_observations: list[Any],
    token_usage: dict[str, Any],
    image_relevant: bool,
    raw_frame_bytes: bytes,
    llm_input_frame_bytes: bytes,
) -> None:
    task = asyncio.create_task(
        maybe_write_vision_inference_trace(
            s3_client=s3_client,
            camera_id=camera_id,
            camera_config_id=camera_config_id,
            image_url=image_url,
            observed_at=observed_at,
            llm_provider=llm_provider,
            llm_model=llm_model,
            system_prompt=system_prompt,
            llm_prompt=llm_prompt,
            structured_output_schema=structured_output_schema,
            entities_with_states=entities_with_states,
            reference_image_metadata=reference_image_metadata,
            raw_llm_response=raw_llm_response,
            entity_observations=entity_observations,
            token_usage=token_usage,
            image_relevant=image_relevant,
            raw_frame_bytes=raw_frame_bytes,
            llm_input_frame_bytes=llm_input_frame_bytes,
        )
    )
    _background_trace_tasks.add(task)
    task.add_done_callback(_background_trace_tasks.discard)
    task.add_done_callback(_log_background_trace_failure)
