"""Tests for monitoring LLM analysis orchestration."""

import base64
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from fastapi import HTTPException


class TestCreateMonitoringRunWithAnalysis:
    """Tests for create_monitoring_run_with_analysis — image run creation."""

    @pytest.mark.asyncio
    async def test_config_not_found_raises_404(self, mocker):
        """Should raise HTTPException 404 when monitoring config not found."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_run_with_analysis(
                session, config_id, "test-image.jpg"
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_business_hours_skip(self, mocker):
        """Should create skipped run when outside business hours."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Mock config
        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {"skip_outside_business_hours": True}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        # Mock run repo
        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        # Mock project repo
        mock_project = MagicMock()
        mock_project.business_hours = {"regular_hours": {"periods": []}}
        mock_project.timezone = "UTC"

        mock_project_repo = mocker.patch(
            "services.monitoring_service._llm.ProjectRepositoryAsync"
        )
        mock_project_repo.return_value.get_project = AsyncMock(
            return_value=mock_project
        )

        # Mock business hours check to say "closed"
        from services.monitoring_service._business_hours import BusinessHoursCheckResult

        mock_hours_result = BusinessHoursCheckResult(
            is_open=False,
            reason="outside_regular_hours",
            period_info={"day": 1},
        )
        mocker.patch(
            "services.monitoring_service._llm.is_within_business_hours",
            return_value=mock_hours_result,
        )
        mocker.patch(
            "services.monitoring_service._llm.parse_captured_at",
            return_value=datetime(2024, 6, 15, 3, 0, 0, tzinfo=timezone.utc),
        )

        trigger_metadata = {"captured_at": "2024-06-15T03:00:00Z"}
        run, details = await create_monitoring_run_with_analysis(
            session, config_id, "test-image.jpg", trigger_metadata
        )

        assert run == mock_created_run
        assert details["analysis_result"]["result"] == "skipped"
        assert details["analysis_result"]["reason"] == "outside_business_hours"
        assert details["skipped"] is True

    @pytest.mark.asyncio
    async def test_time_window_skip(self, mocker):
        """Should create skipped run when outside time window."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {
            "monitoring_time_window": {
                "enabled": True,
                "start_time": "06:00",
                "end_time": "22:00",
            }
        }

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        # Mock should_skip_monitoring to return True
        mocker.patch(
            "services.monitoring_service._llm.should_skip_monitoring",
            return_value=(True, "Outside monitoring time window"),
        )

        run, details = await create_monitoring_run_with_analysis(
            session, config_id, "test-image.jpg"
        )

        assert run == mock_created_run
        assert details["analysis_result"]["result"] == "skipped"
        assert details["analysis_result"]["reason"] == "outside_time_window"

    @pytest.mark.asyncio
    async def test_successful_analysis(self, mocker):
        """Should create run with LLM evaluation_result on successful analysis."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_created_run.id = uuid.uuid4()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        # Mock generate_monitoring_llm_prompt
        analysis_details = {
            "prompt_sent": {"system_instruction": "test"},
            "analysis_result": {"result": "pass", "details": "All clear"},
        }
        mocker.patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            return_value=analysis_details,
        )

        run, details = await create_monitoring_run_with_analysis(
            session, config_id, "test-image.jpg"
        )

        assert run == mock_created_run
        assert details["analysis_result"]["result"] == "pass"
        # Verify MonitoringRun was created with correct result
        create_call = mock_run_repo.return_value.create.call_args[0][0]
        assert create_call.evaluation_result == {
            "result": "pass",
            "details": "All clear",
        }
        assert create_call.error_message is None

    @pytest.mark.asyncio
    async def test_llm_error_result_sets_error_message(self, mocker):
        """Should set error_message when LLM returns error result."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_created_run.id = uuid.uuid4()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        analysis_details = {
            "prompt_sent": {},
            "analysis_result": {
                "result": "error",
                "details": "Image is completely black",
            },
        }
        mocker.patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            return_value=analysis_details,
        )

        run, details = await create_monitoring_run_with_analysis(
            session, config_id, "test-image.jpg"
        )

        create_call = mock_run_repo.return_value.create.call_args[0][0]
        assert create_call.error_message == "Image is completely black"

    @pytest.mark.asyncio
    async def test_llm_api_failure_creates_error_run(self, mocker):
        """Should create error run and re-raise when LLM API call fails."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_error_run = MagicMock()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_error_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        # Make LLM call fail with 500
        mocker.patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            side_effect=HTTPException(status_code=500, detail="LLM API failed"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_run_with_analysis(
                session, config_id, "test-image.jpg"
            )
        assert exc_info.value.status_code == 500

        # Verify error run was created
        mock_run_repo.return_value.create.assert_called_once()
        error_run_arg = mock_run_repo.return_value.create.call_args[0][0]
        assert error_run_arg.error_message == "LLM analysis failed"

    @pytest.mark.asyncio
    async def test_default_trigger_metadata_populated(self, mocker):
        """Should populate default trigger_metadata when None is passed."""
        from services.monitoring_service._llm import create_monitoring_run_with_analysis

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_created_run.id = uuid.uuid4()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        analysis_details = {
            "prompt_sent": {},
            "analysis_result": {"result": "pass", "details": "OK"},
        }
        mocker.patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            return_value=analysis_details,
        )

        await create_monitoring_run_with_analysis(
            session, config_id, "test-image.jpg", trigger_metadata=None
        )

        create_call = mock_run_repo.return_value.create.call_args[0][0]
        assert create_call.trigger_metadata is not None
        assert create_call.trigger_metadata["trigger_source"] == "internal_api"
        assert create_call.trigger_metadata["image_url"] == "test-image.jpg"


class TestCreateMonitoringVideoRunWithAnalysis:
    """Tests for create_monitoring_video_run_with_analysis — video run creation."""

    @pytest.mark.asyncio
    async def test_config_not_found_raises_404(self, mocker):
        """Should raise HTTPException 404 when monitoring config not found."""
        from services.monitoring_service._llm import (
            create_monitoring_video_run_with_analysis,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_video_run_with_analysis(
                session, config_id, "test-video.mp4"
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_business_hours_skip(self, mocker):
        """Should create skipped run when outside business hours."""
        from services.monitoring_service._llm import (
            create_monitoring_video_run_with_analysis,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {"skip_outside_business_hours": True}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mock_project = MagicMock()
        mock_project.business_hours = {}
        mock_project.timezone = "UTC"
        mock_project_repo = mocker.patch(
            "services.monitoring_service._llm.ProjectRepositoryAsync"
        )
        mock_project_repo.return_value.get_project = AsyncMock(
            return_value=mock_project
        )

        from services.monitoring_service._business_hours import BusinessHoursCheckResult

        mocker.patch(
            "services.monitoring_service._llm.is_within_business_hours",
            return_value=BusinessHoursCheckResult(
                is_open=False, reason="outside_regular_hours"
            ),
        )
        mocker.patch(
            "services.monitoring_service._llm.parse_captured_at",
            return_value=datetime(2024, 6, 15, 3, 0, 0, tzinfo=timezone.utc),
        )

        trigger_metadata = {"captured_at": "2024-06-15T03:00:00Z"}
        run, details = await create_monitoring_video_run_with_analysis(
            session, config_id, "test-video.mp4", trigger_metadata
        )

        assert details["analysis_result"]["result"] == "skipped"
        assert details["analysis_result"]["reason"] == "outside_business_hours"

    @pytest.mark.asyncio
    async def test_time_window_skip(self, mocker):
        """Should create skipped run when outside time window."""
        from services.monitoring_service._llm import (
            create_monitoring_video_run_with_analysis,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {
            "monitoring_time_window": {
                "enabled": True,
                "start_time": "06:00",
                "end_time": "22:00",
            }
        }

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        mocker.patch(
            "services.monitoring_service._llm.should_skip_monitoring",
            return_value=(True, "Outside monitoring time window"),
        )

        run, details = await create_monitoring_video_run_with_analysis(
            session, config_id, "test-video.mp4"
        )

        assert details["analysis_result"]["result"] == "skipped"
        assert details["analysis_result"]["reason"] == "outside_time_window"

    @pytest.mark.asyncio
    async def test_successful_video_analysis(self, mocker):
        """Should create run with evaluation_result on successful video analysis."""
        from services.monitoring_service._llm import (
            create_monitoring_video_run_with_analysis,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_created_run = MagicMock()
        mock_created_run.id = uuid.uuid4()
        mock_run_repo.return_value.create = AsyncMock(return_value=mock_created_run)

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        analysis_details = {
            "prompt_sent": {"system_instruction": "test"},
            "analysis_result": {"result": "fail", "details": "Anomaly detected"},
        }
        mocker.patch(
            "services.monitoring_service._llm.generate_monitoring_video_llm_prompt",
            return_value=analysis_details,
        )

        run, details = await create_monitoring_video_run_with_analysis(
            session, config_id, "test-video.mp4"
        )

        assert run == mock_created_run
        assert details["analysis_result"]["result"] == "fail"

    @pytest.mark.asyncio
    async def test_llm_failure_creates_error_run(self, mocker):
        """Should create error run and re-raise when LLM video analysis fails."""
        from services.monitoring_service._llm import (
            create_monitoring_video_run_with_analysis,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

        mock_run_repo = mocker.patch(
            "services.monitoring_service._llm.MonitoringRunRepositoryAsync"
        )
        mock_run_repo.return_value.create = AsyncMock(return_value=MagicMock())

        mocker.patch("services.monitoring_service._llm.ProjectRepositoryAsync")

        mocker.patch(
            "services.monitoring_service._llm.generate_monitoring_video_llm_prompt",
            side_effect=HTTPException(
                status_code=500, detail="LLM video analysis failed"
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_video_run_with_analysis(
                session, config_id, "test-video.mp4"
            )
        assert exc_info.value.status_code == 500

        # Verify error run was created
        error_run_arg = mock_run_repo.return_value.create.call_args[0][0]
        assert error_run_arg.error_message == "LLM video analysis failed"


def _build_image_analysis_mocks(mocker, config_id):
    """Set up common mocks for generate_monitoring_llm_prompt tests."""
    mock_config = MagicMock()
    mock_config.rules = {
        "prompt": "Check the display",
        "reference_images": [],
        "model": {"provider": "azure", "model": "gpt-4o"},
    }

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

    # Mock provider creation
    mock_provider = MagicMock()
    mock_provider.config.provider.value = "azure"
    mock_provider.config.model = "gpt-4o"
    mock_provider.analyze_image.return_value = {
        "result": "pass",
        "details": "All clear",
    }
    mocker.patch(
        "services.monitoring_service._llm.create_monitoring_llm_provider",
        return_value=mock_provider,
    )

    return mock_provider


def _build_video_analysis_mocks(mocker, config_id):
    """Set up common mocks for generate_monitoring_video_llm_prompt tests (frame extraction path)."""
    mock_config = MagicMock()
    mock_config.rules = {
        "prompt": "Check the display",
        "reference_images": [],
        "model": {"provider": "azure", "model": "gpt-4o"},
    }

    mock_config_repo = mocker.patch(
        "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
    )
    mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

    # Mock S3
    mock_s3 = MagicMock()
    mocker.patch("services.monitoring_service._llm.boto3.client", return_value=mock_s3)

    # Mock video frame extraction
    mocker.patch(
        "services.monitoring_service._llm.extract_video_frames",
        return_value=[
            {
                "base64_data": base64.b64encode(b"frame1").decode(),
                "timestamp_label": "0:00",
            },
            {
                "base64_data": base64.b64encode(b"frame2").decode(),
                "timestamp_label": "0:05",
            },
        ],
    )

    # Mock supports_native_video to return False (frame extraction path)
    mocker.patch(
        "services.monitoring_service._llm.supports_native_video",
        return_value=False,
    )

    # Mock provider creation
    mock_provider = MagicMock()
    mock_provider.config.provider.value = "azure"
    mock_provider.config.model = "gpt-4o"
    mock_provider.analyze_video_frames.return_value = {
        "result": "pass",
        "details": "All clear",
    }
    mocker.patch(
        "services.monitoring_service._llm.create_monitoring_llm_provider",
        return_value=mock_provider,
    )

    return mock_provider


def _build_native_video_analysis_mocks(mocker, config_id):
    """Set up common mocks for generate_monitoring_video_llm_prompt tests (native video path)."""
    from services.monitoring_service._providers import GoogleMonitoringProvider

    mock_config = MagicMock()
    mock_config.rules = {
        "prompt": "Check the display",
        "reference_images": [],
        "model": {"provider": "google", "model": "gemini-2.5-flash"},
    }

    mock_config_repo = mocker.patch(
        "services.monitoring_service._llm.MonitoringConfigRepositoryAsync"
    )
    mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)

    # Mock S3
    mock_s3 = MagicMock()
    mocker.patch("services.monitoring_service._llm.boto3.client", return_value=mock_s3)

    # Mock supports_native_video to return True
    mocker.patch(
        "services.monitoring_service._llm.supports_native_video",
        return_value=True,
    )

    # Mock download_video_bytes
    mocker.patch(
        "services.monitoring_service._llm.download_video_bytes",
        return_value=(b"fake-video-bytes", "video/mp4"),
    )

    # Mock provider creation — must pass isinstance check for GoogleMonitoringProvider
    mock_provider = MagicMock()
    mock_provider.__class__ = GoogleMonitoringProvider  # type: ignore[misc]
    mock_provider.config.provider.value = "google"
    mock_provider.config.model = "gemini-2.5-flash"
    mock_provider.analyze_native_video.return_value = {
        "result": "pass",
        "details": "All clear from native video",
    }
    mocker.patch(
        "services.monitoring_service._llm.create_monitoring_llm_provider",
        return_value=mock_provider,
    )

    return mock_provider


class TestImageAnalysisTraceIsolation:
    """Tests for trace isolation in generate_monitoring_llm_prompt."""

    @pytest.mark.asyncio
    async def test_clears_context_before_llm_call(self, mocker):
        """Should clear inherited trace context before calling the LLM provider."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_image_analysis_mocks(mocker, config_id)

        # Track tracer calls
        fake_parent_context = MagicMock(name="parent-context")
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = fake_parent_context

        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        # Verify context was cleared (activated with None)
        activate_calls = mock_tracer.context_provider.activate.call_args_list
        assert activate_calls[0] == call(None), "Should clear context before LLM call"

    @pytest.mark.asyncio
    async def test_creates_span_with_correct_operation_and_service(self, mocker):
        """Should create a monitoring span with expected operation name and service."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_image_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        mock_tracer.trace.assert_called_once_with(
            "monitoring.llm.analyze_image",
            service="pal-mono-monitoring",
        )

    @pytest.mark.asyncio
    async def test_sets_expected_monitoring_tags(self, mocker):
        """Should set config_id, provider, model, and media_type tags on span."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_image_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        mock_span.set_tag.assert_any_call("monitoring.config_id", str(config_id))
        mock_span.set_tag.assert_any_call("monitoring.llm_provider", "azure")
        mock_span.set_tag.assert_any_call("monitoring.llm_model", "gpt-4o")
        mock_span.set_tag.assert_any_call("monitoring.media_type", "image")

    @pytest.mark.asyncio
    async def test_restores_context_after_success(self, mocker):
        """Should restore original trace context after successful LLM call."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_image_analysis_mocks(mocker, config_id)

        fake_parent_context = MagicMock(name="parent-context")
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = fake_parent_context
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        # Last activate call should restore the parent context
        activate_calls = mock_tracer.context_provider.activate.call_args_list
        assert activate_calls[-1] == call(
            fake_parent_context
        ), "Should restore original context after LLM call"

    @pytest.mark.asyncio
    async def test_restores_context_on_provider_exception(self, mocker):
        """Should restore original trace context even when provider raises."""
        from services.monitoring_service._llm import generate_monitoring_llm_prompt

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_image_analysis_mocks(mocker, config_id)
        mock_provider.analyze_image.side_effect = RuntimeError("LLM exploded")

        fake_parent_context = MagicMock(name="parent-context")
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = fake_parent_context
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(HTTPException):
            await generate_monitoring_llm_prompt(session, config_id, "img.jpg")

        # Context should still be restored even on error
        activate_calls = mock_tracer.context_provider.activate.call_args_list
        assert activate_calls[-1] == call(
            fake_parent_context
        ), "Should restore context even when provider raises"


class TestVideoAnalysisTraceIsolation:
    """Tests for trace isolation in generate_monitoring_video_llm_prompt."""

    @pytest.mark.asyncio
    async def test_clears_context_before_llm_call(self, mocker):
        """Should clear inherited trace context before calling the LLM provider."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_video_analysis_mocks(mocker, config_id)

        fake_parent_context = MagicMock(name="parent-context")
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = fake_parent_context
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        activate_calls = mock_tracer.context_provider.activate.call_args_list
        assert activate_calls[0] == call(None), "Should clear context before LLM call"

    @pytest.mark.asyncio
    async def test_creates_span_with_correct_operation_and_service(self, mocker):
        """Should create a monitoring span with expected operation name and service."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_video_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        mock_tracer.trace.assert_called_once_with(
            "monitoring.llm.analyze_video_frames",
            service="pal-mono-monitoring",
        )

    @pytest.mark.asyncio
    async def test_sets_expected_monitoring_tags_including_frames_count(self, mocker):
        """Should set config_id, provider, model, media_type, and frames_count tags."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_video_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        mock_span.set_tag.assert_any_call("monitoring.config_id", str(config_id))
        mock_span.set_tag.assert_any_call("monitoring.llm_provider", "azure")
        mock_span.set_tag.assert_any_call("monitoring.llm_model", "gpt-4o")
        mock_span.set_tag.assert_any_call("monitoring.media_type", "video")
        mock_span.set_tag.assert_any_call("monitoring.video_frames_count", "2")

    @pytest.mark.asyncio
    async def test_restores_context_after_success(self, mocker):
        """Should restore original trace context after successful LLM call."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_video_analysis_mocks(mocker, config_id)

        fake_parent_context = MagicMock(name="parent-context")
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = fake_parent_context
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        activate_calls = mock_tracer.context_provider.activate.call_args_list
        assert activate_calls[-1] == call(
            fake_parent_context
        ), "Should restore original context after LLM call"

    @pytest.mark.asyncio
    async def test_restores_context_on_provider_exception(self, mocker):
        """Should restore original trace context even when provider raises."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_video_analysis_mocks(mocker, config_id)
        mock_provider.analyze_video_frames.side_effect = RuntimeError("LLM exploded")

        fake_parent_context = MagicMock(name="parent-context")
        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = fake_parent_context
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(HTTPException):
            await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        activate_calls = mock_tracer.context_provider.activate.call_args_list
        assert activate_calls[-1] == call(
            fake_parent_context
        ), "Should restore context even when provider raises"


class TestNativeVideoAnalysis:
    """Tests for native video path in generate_monitoring_video_llm_prompt."""

    @pytest.mark.asyncio
    async def test_uses_native_video_when_supported(self, mocker):
        """Should call analyze_native_video instead of analyze_video_frames for supported models."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_native_video_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        result = await generate_monitoring_video_llm_prompt(
            session, config_id, "vid.mp4"
        )

        # Should call analyze_native_video, not analyze_video_frames
        mock_provider.analyze_native_video.assert_called_once()
        mock_provider.analyze_video_frames.assert_not_called()
        assert result["analysis_result"]["result"] == "pass"

    @pytest.mark.asyncio
    async def test_native_video_downloads_raw_bytes(self, mocker):
        """Should call download_video_bytes instead of extract_video_frames."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_native_video_analysis_mocks(mocker, config_id)

        mock_download = mocker.patch(
            "services.monitoring_service._llm.download_video_bytes",
            return_value=(b"video-data", "video/mp4"),
        )
        mock_extract = mocker.patch(
            "services.monitoring_service._llm.extract_video_frames",
        )

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        mock_download.assert_called_once_with("vid.mp4")
        mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_native_video_prompt_summary_includes_metadata(self, mocker):
        """Should include native_video flag and video_size_bytes in prompt summary."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_native_video_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        result = await generate_monitoring_video_llm_prompt(
            session, config_id, "vid.mp4"
        )

        prompt = result["prompt_sent"]
        assert prompt["native_video"] is True
        assert prompt["video_size_bytes"] == len(b"fake-video-bytes")
        assert "video_frames_count" not in prompt

    @pytest.mark.asyncio
    async def test_native_video_trace_tags(self, mocker):
        """Should set native_video media_type and video_size_bytes tags on span."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        _build_native_video_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        await generate_monitoring_video_llm_prompt(session, config_id, "vid.mp4")

        mock_tracer.trace.assert_called_once_with(
            "monitoring.llm.analyze_native_video",
            service="pal-mono-monitoring",
        )
        mock_span.set_tag.assert_any_call("monitoring.media_type", "native_video")
        mock_span.set_tag.assert_any_call(
            "monitoring.video_size_bytes", str(len(b"fake-video-bytes"))
        )
        mock_span.set_tag.assert_any_call("monitoring.video_mime_type", "video/mp4")

    @pytest.mark.asyncio
    async def test_falls_back_to_frames_when_not_supported(self, mocker):
        """Should use frame extraction when model does not support native video."""
        from services.monitoring_service._llm import (
            generate_monitoring_video_llm_prompt,
        )

        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_provider = _build_video_analysis_mocks(mocker, config_id)

        mock_tracer = mocker.patch("services.monitoring_service._llm.tracer")
        mock_tracer.current_trace_context.return_value = MagicMock()
        mock_span = MagicMock()
        mock_tracer.trace.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.trace.return_value.__exit__ = MagicMock(return_value=False)

        result = await generate_monitoring_video_llm_prompt(
            session, config_id, "vid.mp4"
        )

        mock_provider.analyze_video_frames.assert_called_once()
        assert "video_frames_count" in result["prompt_sent"]
        assert "native_video" not in result["prompt_sent"]
