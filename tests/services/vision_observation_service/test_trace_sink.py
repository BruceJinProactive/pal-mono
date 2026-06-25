"""Tests for Vision observation inference trace sink."""

import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from api.schemas.operations.vision_observation import EntityObservation
from services.vision_observation_service._trace_sink import (
    maybe_write_vision_inference_trace,
    should_write_vision_inference_trace,
)
from utils.log import request_id_ctx


@pytest.mark.parametrize(
    "runtime_env",
    [None, "dev", "local", "lat", "prd", "production", "unknown"],
)
def test_trace_uses_hardcoded_sample_rate_in_all_envs(
    runtime_env: str | None,
) -> None:
    camera_config_id = uuid.uuid4()
    env = {} if runtime_env is None else {"RUNTIME_ENV": runtime_env}

    with (
        patch.dict(os.environ, env, clear=True),
        patch("services.vision_observation_service._trace_sink.random.random") as rand,
    ):
        rand.return_value = 0.999
        assert should_write_vision_inference_trace(camera_config_id) is True

        rand.return_value = 1.0
        assert should_write_vision_inference_trace(camera_config_id) is False


@pytest.mark.asyncio
async def test_maybe_write_trace_uploads_images_and_scrubbed_json() -> None:
    camera_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    state_id = uuid.uuid4()
    observed_at = datetime(2026, 6, 25, 1, 2, 3, tzinfo=timezone.utc)
    s3_client = MagicMock()
    request_token = request_id_ctx.set("req-abc-123")

    try:
        with (
            patch.dict(
                os.environ,
                {
                    "RUNTIME_ENV": "lat",
                    "BUILD_SHA": "sha123",
                },
                clear=True,
            ),
            patch(
                "services.vision_observation_service._trace_sink.random.random",
                return_value=0.004,
            ),
        ):
            result = await maybe_write_vision_inference_trace(
                s3_client=s3_client,
                camera_id=camera_id,
                camera_config_id=camera_config_id,
                image_url="frames/camera/frame.jpg",
                observed_at=observed_at,
                llm_provider="google",
                llm_model="gemini-2.5-flash",
                system_prompt="system prompt",
                llm_prompt="analysis prompt",
                structured_output_schema={"type": "object"},
                entities_with_states=[
                    {
                        "name": "table_1",
                        "roi_hint": {"x": 10, "y": 20, "width": 30, "height": 40},
                    }
                ],
                reference_image_metadata=[
                    {
                        "url": "refs/table.jpg",
                        "description": "Reference",
                        "base64_data": "do-not-store",
                        "thumbnail": "data:image/jpeg;base64,also-do-not-store",
                    }
                ],
                raw_llm_response={
                    "table_1": {
                        "cleanliness": {
                            "state": "clean",
                            "confidence": 0.91,
                            "reason": "No dishes visible",
                        }
                    },
                    "image_relevant": True,
                },
                entity_observations=[
                    EntityObservation(
                        entity_id=entity_id,
                        entity_name="table_1",
                        camera_id=camera_id,
                        definition_type="cleanliness",
                        state="clean",
                        state_id=state_id,
                        confidence=0.91,
                    )
                ],
                token_usage={"prompt_tokens": 12, "observed": True},
                image_relevant=True,
                raw_frame_bytes=b"raw-frame",
                llm_input_frame_bytes=b"overlay-frame",
            )
    finally:
        request_id_ctx.reset(request_token)

    assert result is not None
    assert result.trace_id == "req-abc-123"
    assert "/env=lat/dt=2026-06-25/hour=01/" in result.trace_s3_key
    assert result.trace_s3_key.endswith("/trace.json")

    put_calls = s3_client.put_object.call_args_list
    assert len(put_calls) == 3
    assert put_calls[0].kwargs["Key"] == result.raw_frame_s3_key
    assert put_calls[0].kwargs["Body"] == b"raw-frame"
    assert put_calls[0].kwargs["ContentType"] == "image/jpeg"
    assert put_calls[1].kwargs["Key"] == result.llm_input_frame_s3_key
    assert put_calls[1].kwargs["Body"] == b"overlay-frame"
    assert put_calls[1].kwargs["ContentType"] == "image/jpeg"
    assert put_calls[2].kwargs["Key"] == result.trace_s3_key
    assert put_calls[2].kwargs["ContentType"] == "application/json"

    trace_json = json.loads(put_calls[2].kwargs["Body"].decode("utf-8"))
    assert trace_json["trace_id"] == "req-abc-123"
    assert trace_json["camera_id"] == str(camera_id)
    assert trace_json["camera_config_id"] == str(camera_config_id)
    assert trace_json["system_prompt"] == "system prompt"
    assert trace_json["analysis_task"] == "analysis prompt"
    assert trace_json["structured_output_schema"] == {"type": "object"}
    assert trace_json["raw_llm_response"]["table_1"]["cleanliness"]["state"] == "clean"
    assert trace_json["entity_observations"][0]["state_id"] == str(state_id)
    assert trace_json["token_usage"] == {"observed": True, "prompt_tokens": 12}
    assert trace_json["artifacts"]["raw_frame_s3_key"] == result.raw_frame_s3_key
    assert (
        trace_json["artifacts"]["llm_input_frame_s3_key"]
        == result.llm_input_frame_s3_key
    )
    assert "base64_data" not in trace_json["reference_images"][0]
    assert trace_json["reference_images"][0]["thumbnail"] == "<data image omitted>"
    assert trace_json["build_sha"] == "sha123"


@pytest.mark.asyncio
async def test_trace_write_failure_logs_warning_and_returns_none() -> None:
    camera_id = uuid.uuid4()
    camera_config_id = uuid.uuid4()
    s3_client = MagicMock()
    s3_client.put_object.side_effect = RuntimeError("s3 unavailable")

    with (
        patch.dict(
            os.environ,
            {"RUNTIME_ENV": "lat"},
            clear=True,
        ),
        patch(
            "services.vision_observation_service._trace_sink.random.random",
            return_value=0.004,
        ),
        patch("services.vision_observation_service._trace_sink.logger.warning") as warn,
    ):
        result = await maybe_write_vision_inference_trace(
            s3_client=s3_client,
            camera_id=camera_id,
            camera_config_id=camera_config_id,
            image_url=None,
            observed_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
            llm_provider="azure",
            llm_model="gpt-4o",
            system_prompt="system prompt",
            llm_prompt="analysis prompt",
            structured_output_schema={},
            entities_with_states=[],
            reference_image_metadata=[],
            raw_llm_response={},
            entity_observations=[],
            token_usage={},
            image_relevant=True,
            raw_frame_bytes=b"raw-frame",
            llm_input_frame_bytes=b"overlay-frame",
        )

    assert result is None
    warn.assert_called_once()
    assert warn.call_args.args[0] == (
        "[Vision Observation Trace] Failed to write inference trace"
    )


@pytest.mark.asyncio
async def test_sample_miss_does_not_call_s3_upload_helper() -> None:
    s3_client = MagicMock()

    with patch(
        "services.vision_observation_service._trace_sink.random.random",
        return_value=1.0,
    ):
        result = await maybe_write_vision_inference_trace(
            s3_client=s3_client,
            camera_id=uuid.uuid4(),
            camera_config_id=uuid.uuid4(),
            image_url=None,
            observed_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
            llm_provider="azure",
            llm_model="gpt-4o",
            system_prompt="system prompt",
            llm_prompt="analysis prompt",
            structured_output_schema={},
            entities_with_states=[],
            reference_image_metadata=[],
            raw_llm_response={},
            entity_observations=[],
            token_usage={},
            image_relevant=True,
            raw_frame_bytes=b"raw-frame",
            llm_input_frame_bytes=b"overlay-frame",
        )

    assert result is None
    s3_client.put_object.assert_not_called()
