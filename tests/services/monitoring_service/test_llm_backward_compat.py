"""Tests for monitoring config restructure — LLM backward compatibility.

Validates that the LLM prompt generation functions:
- Prefer 'context' field, fall back to 'prompt' for legacy configs
- Include pass_criteria and fail_criteria in the analysis task
- Include reference image flag labels in image descriptions
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


def _build_llm_mocks(mocker, rules: dict):
    """Set up common mocks for generate_monitoring_llm_prompt tests."""
    mock_config = MagicMock()
    mock_config.rules = rules
    model_rules = rules.get("model", {})
    provider_name = model_rules.get("provider", "azure")
    model_name = model_rules.get("model", "gpt-4o")

    mock_config_repo = mocker.patch(
        "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
    )
    mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

    # Mock S3 — camera image fetch
    mock_s3 = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = b"fake-image-bytes"
    mock_s3.get_object.return_value = {"Body": mock_body}
    mocker.patch("services.monitoring_service._llm.boto3.client", return_value=mock_s3)

    # Mock provider
    mock_provider = MagicMock()
    mock_provider.config.provider.value = provider_name
    mock_provider.config.model = model_name
    mock_provider.analyze_image.return_value = {
        "result": {"result": "pass", "details": "All clear"},
        "token_usage": {
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "total_tokens": 550,
        },
    }
    mocker.patch(
        "services.monitoring_service._llm.create_monitoring_llm_provider",
        return_value=mock_provider,
    )

    # Mock OTel tracer
    mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
        return_value=mock_span
    )
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
        return_value=False
    )

    # Mock OTel context isolation
    mock_otel_context = mocker.patch("services.monitoring_service._llm.otel_context")
    mock_otel_context.attach.return_value = "mock-token"
    mocker.patch("services.monitoring_service._llm.Context")

    # Mock statsd
    mocker.patch("services.monitoring_service._llm.statsd")

    return mock_provider


class TestLLMContextBackwardCompat:
    """Test that generate_monitoring_llm_prompt handles both context and prompt."""

    @pytest.mark.asyncio
    async def test_reads_context_field_from_new_config(self, mocker) -> None:
        """New configs with 'context' field should be used for the analysis task."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen area during business hours",
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "Kitchen area during business hours" in analysis_task_text

    @pytest.mark.asyncio
    async def test_falls_back_to_prompt_for_legacy_config(self, mocker) -> None:
        """Legacy configs with only 'prompt' field should still work."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "prompt": "Check if kitchen is clean",
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "Check if kitchen is clean" in analysis_task_text

    @pytest.mark.asyncio
    async def test_context_preferred_over_prompt(self, mocker) -> None:
        """When both context and prompt exist, context should be used."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "New context description",
                "prompt": "Old legacy prompt",
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "New context description" in analysis_task_text

    @pytest.mark.asyncio
    async def test_no_context_or_prompt_raises_error(self, mocker) -> None:
        """Config with neither context nor prompt should raise HTTP 400."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_llm_mocks(
            mocker,
            rules={
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await generate_monitoring_llm_prompt(session, config_id, "img.jpg")
        assert exc_info.value.status_code == 400


class TestLLMCriteriaInPrompt:
    """Test that pass/fail criteria are included in the LLM analysis task."""

    @pytest.mark.asyncio
    async def test_pass_criteria_in_analysis_task(self, mocker) -> None:
        """Analysis task should include pass criteria when available."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen monitoring",
                "pass_criteria": ["All surfaces clean", "Equipment properly stored"],
                "fail_criteria": [],
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "All surfaces clean" in analysis_task_text
        assert "Equipment properly stored" in analysis_task_text

    @pytest.mark.asyncio
    async def test_fail_criteria_in_analysis_task(self, mocker) -> None:
        """Analysis task should include fail criteria when available."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen monitoring",
                "pass_criteria": [],
                "fail_criteria": ["Visible debris on surfaces", "Equipment left out"],
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "Visible debris on surfaces" in analysis_task_text
        assert "Equipment left out" in analysis_task_text

    @pytest.mark.asyncio
    async def test_legacy_config_without_criteria_still_works(self, mocker) -> None:
        """Legacy configs without criteria should still produce valid analysis task."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_llm_mocks(
            mocker,
            rules={
                "prompt": "Check the kitchen",
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        # Should NOT raise — legacy configs are valid
        result = await generate_monitoring_llm_prompt(session, config_id, "img.jpg")
        assert result["analysis_result"]["result"] == "pass"


class TestLLMStructuredOutputDefaults:
    """Test that monitoring prompt generation always provides a JSON schema."""

    @pytest.mark.asyncio
    async def test_default_schema_sent_when_structured_output_missing(
        self, mocker
    ) -> None:
        """Legacy/default monitoring configs should still use structured outputs."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "Check the prep station",
                "reference_images": [],
                "model": {"provider": "google", "model": "gemini-3-flash-preview"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        response_format = (
            call_kwargs.kwargs.get("response_format")
            or call_kwargs[1]["response_format"]
        )
        schema = response_format["json_schema"]["schema"]

        assert response_format["type"] == "json_schema"
        assert schema["required"] == ["result", "details"]
        assert schema["properties"]["result"]["enum"] == ["pass", "fail", "error"]
        assert schema["properties"]["confidence"]["type"] == "integer"


class TestLLMReferenceImageFlags:
    """Test that reference image flags are reflected in LLM descriptions."""

    @pytest.mark.asyncio
    async def test_pass_flag_label_in_description(self, mocker) -> None:
        """Pass-flagged images should include pass label in LLM description."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen check",
                "reference_images": [
                    {
                        "id": "img1",
                        "url": "ref/img1.jpg",
                        "description": "Clean counter",
                        "flag": "pass",
                    },
                ],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        ref_images = call_kwargs.kwargs.get("reference_images") or call_kwargs[1].get(
            "reference_images"
        )
        # The description sent to LLM should indicate PASS example
        assert len(ref_images) == 1
        desc = ref_images[0]["description"].upper()
        assert "PASS" in desc

    @pytest.mark.asyncio
    async def test_fail_flag_label_in_description(self, mocker) -> None:
        """Fail-flagged images should include fail label in LLM description."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen check",
                "reference_images": [
                    {
                        "id": "img1",
                        "url": "ref/img1.jpg",
                        "description": "Dirty counter",
                        "flag": "fail",
                    },
                ],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        call_kwargs = mock_provider.analyze_image.call_args
        ref_images = call_kwargs.kwargs.get("reference_images") or call_kwargs[1].get(
            "reference_images"
        )
        assert len(ref_images) == 1
        desc = ref_images[0]["description"].upper()
        assert "FAIL" in desc

    @pytest.mark.asyncio
    async def test_legacy_images_without_flag_treated_as_pass(self, mocker) -> None:
        """Legacy images without flag field should be treated as pass examples."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_llm_mocks(
            mocker,
            rules={
                "prompt": "Kitchen check",
                "reference_images": [
                    {
                        "id": "img1",
                        "url": "ref/img1.jpg",
                        "description": "Kitchen view",
                    },
                    # No "flag" field — legacy format
                ],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        # Should NOT raise
        result = await generate_monitoring_llm_prompt(session, config_id, "img.jpg")
        assert result is not None

        call_kwargs = mock_provider.analyze_image.call_args
        ref_images = call_kwargs.kwargs.get("reference_images") or call_kwargs[1].get(
            "reference_images"
        )
        assert len(ref_images) == 1
        # Legacy image (no flag) should default to pass label
        desc = ref_images[0]["description"].upper()
        assert "PASS" in desc


def _build_video_llm_mocks(mocker, rules: dict):
    """Set up common mocks for generate_monitoring_video_llm_prompt tests."""
    mock_config = MagicMock()
    mock_config.rules = rules
    model_rules = rules.get("model", {})
    provider_name = model_rules.get("provider", "azure")
    model_name = model_rules.get("model", "gpt-4o")

    mock_config_repo = mocker.patch(
        "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
    )
    mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

    # Mock S3 — reference image fetch
    mock_s3 = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = b"fake-image-bytes"
    mock_s3.get_object.return_value = {"Body": mock_body}
    mocker.patch("services.monitoring_service._llm.boto3.client", return_value=mock_s3)

    # Mock video frame extraction (frame-based path)
    mocker.patch(
        "services.monitoring_service._llm.extract_video_frames",
        new_callable=AsyncMock,
        return_value=["ZmFrZS1mcmFtZS0x", "ZmFrZS1mcmFtZS0y"],
    )
    # Force frame extraction path (not native video)
    mocker.patch(
        "services.monitoring_service._llm.supports_native_video",
        return_value=False,
    )

    # Mock provider
    mock_provider = MagicMock()
    mock_provider.config.provider.value = provider_name
    mock_provider.config.model = model_name
    mock_provider.analyze_video_frames.return_value = {
        "result": {"result": "pass", "details": "All clear"},
        "token_usage": {
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "total_tokens": 550,
        },
    }
    mocker.patch(
        "services.monitoring_service._llm.create_monitoring_llm_provider",
        return_value=mock_provider,
    )

    # Mock OTel tracer
    mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
        return_value=mock_span
    )
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
        return_value=False
    )

    # Mock OTel context isolation
    mock_otel_context = mocker.patch("services.monitoring_service._llm.otel_context")
    mock_otel_context.attach.return_value = "mock-token"
    mocker.patch("services.monitoring_service._llm.Context")

    # Mock statsd
    mocker.patch("services.monitoring_service._llm.statsd")

    return mock_provider


class TestVideoLLMContextBackwardCompat:
    """Test that generate_monitoring_video_llm_prompt handles context, criteria, and flags."""

    @pytest.mark.asyncio
    async def test_video_reads_context_field_from_new_config(self, mocker) -> None:
        """New video configs with 'context' should be used for the analysis task."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_video_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen area during business hours",
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_video_llm_prompt(session, config_id, "video.mp4")

        call_kwargs = mock_provider.analyze_video_frames.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "Kitchen area during business hours" in analysis_task_text

    @pytest.mark.asyncio
    async def test_video_falls_back_to_prompt_for_legacy_config(self, mocker) -> None:
        """Legacy video configs with only 'prompt' should still work."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_video_llm_mocks(
            mocker,
            rules={
                "prompt": "Check if kitchen is clean",
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_video_llm_prompt(session, config_id, "video.mp4")

        call_kwargs = mock_provider.analyze_video_frames.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "Check if kitchen is clean" in analysis_task_text

    @pytest.mark.asyncio
    async def test_video_criteria_in_analysis_task(self, mocker) -> None:
        """Video analysis task should include pass and fail criteria."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_video_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen monitoring",
                "pass_criteria": ["All surfaces clean", "Equipment properly stored"],
                "fail_criteria": ["Visible debris on surfaces"],
                "reference_images": [],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        await generate_monitoring_video_llm_prompt(session, config_id, "video.mp4")

        call_kwargs = mock_provider.analyze_video_frames.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "All surfaces clean" in analysis_task_text
        assert "Equipment properly stored" in analysis_task_text
        assert "Visible debris on surfaces" in analysis_task_text


class TestNativeVideoLLMCriteria:
    """Test that native video path includes criteria in the analysis task."""

    @pytest.mark.asyncio
    async def test_native_video_includes_pass_and_fail_criteria(self, mocker) -> None:
        """Native video path should include pass and fail criteria in analysis task."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )
        from services.monitoring_service._providers import GoogleMonitoringProvider

        session = AsyncMock()
        config_id = uuid.uuid4()

        rules = {
            "context": "Kitchen monitoring",
            "pass_criteria": ["All surfaces clean"],
            "fail_criteria": ["Visible debris on surfaces"],
            "reference_images": [],
            "model": {"provider": "google", "model": "gemini-2.0-flash"},
        }

        mock_config = MagicMock()
        mock_config.rules = rules

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        # Mock S3
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake-image-bytes"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mocker.patch(
            "services.monitoring_service._llm.boto3.client", return_value=mock_s3
        )

        # Enable native video path
        mocker.patch(
            "services.monitoring_service._llm.supports_native_video",
            return_value=True,
        )

        # Mock download_video_bytes
        mocker.patch(
            "services.monitoring_service._llm.download_video_bytes",
            new_callable=AsyncMock,
            return_value=(b"fake-video-bytes", "video/mp4"),
        )

        # Provider must be GoogleMonitoringProvider for native video
        mock_provider = MagicMock(spec=GoogleMonitoringProvider)
        mock_config_obj = MagicMock()
        mock_config_obj.provider.value = "google"
        mock_config_obj.model = "gemini-2.0-flash"
        mock_provider.config = mock_config_obj
        mock_provider.analyze_native_video.return_value = {
            "result": {"result": "pass", "details": "All clear"},
            "token_usage": {
                "prompt_tokens": 500,
                "completion_tokens": 50,
                "total_tokens": 550,
            },
        }
        mocker.patch(
            "services.monitoring_service._llm.create_monitoring_llm_provider",
            return_value=mock_provider,
        )

        # Mock OTel tracer
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        # Mock OTel context isolation
        mock_otel_context = mocker.patch(
            "services.monitoring_service._llm.otel_context"
        )
        mock_otel_context.attach.return_value = "mock-token"
        mocker.patch("services.monitoring_service._llm.Context")

        # Mock statsd
        mocker.patch("services.monitoring_service._llm.statsd")

        await generate_monitoring_video_llm_prompt(session, config_id, "video.mp4")

        call_kwargs = mock_provider.analyze_native_video.call_args
        analysis_task_text = call_kwargs.kwargs.get("analysis_task") or call_kwargs[
            1
        ].get("analysis_task")
        assert "All surfaces clean" in analysis_task_text
        assert "Visible debris on surfaces" in analysis_task_text
        assert "Pass Criteria" in analysis_task_text
        assert "Fail Criteria" in analysis_task_text


class TestVideoLLMReferenceImageFlags:
    """Test that video reference image flags are included in LLM descriptions."""

    @pytest.mark.asyncio
    async def test_video_ref_image_flag_label_in_description(self, mocker) -> None:
        """Video reference images should include flag label in LLM description."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_video_llm_mocks(
            mocker,
            rules={
                "context": "Kitchen check",
                "reference_images": [
                    {
                        "id": "img1",
                        "url": "ref/img1.jpg",
                        "description": "Clean counter",
                        "flag": "pass",
                    },
                    {
                        "id": "img2",
                        "url": "ref/img2.jpg",
                        "description": "Dirty counter",
                        "flag": "fail",
                    },
                ],
                "model": {"provider": "azure", "model": "gpt-4o"},
            },
        )

        # Mock asyncio.to_thread to run synchronously for coverage
        mocker.patch(
            "services.monitoring_service._llm.asyncio.to_thread",
            side_effect=lambda fn, *a, **kw: fn(*a, **kw),
        )

        await generate_monitoring_video_llm_prompt(session, config_id, "video.mp4")

        call_kwargs = mock_provider.analyze_video_frames.call_args
        ref_images = call_kwargs.kwargs.get("reference_images") or call_kwargs[1].get(
            "reference_images"
        )
        assert len(ref_images) == 2
        assert "PASS" in ref_images[0]["description"].upper()
        assert "FAIL" in ref_images[1]["description"].upper()
