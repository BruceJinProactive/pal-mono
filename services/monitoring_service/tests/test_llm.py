"""Tests for monitoring LLM analysis orchestration."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
