"""Tests for internal monitoring API endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.routes.internal.monitoring import RecordCaptureRequest, record_capture


class TestRecordCapture:
    """Test coverage for record_capture endpoint."""

    @pytest.mark.asyncio
    async def test_record_capture_success_with_metrics(self):
        """Test successful capture recording emits monitoring.camera.feed.updated metric."""
        signal_source_id = uuid.uuid4()
        feed_id = uuid.uuid4()
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        captured_at = datetime.now(timezone.utc)

        request = RecordCaptureRequest(
            signal_source_id=signal_source_id,
            captured_at=captured_at,
            capture_url="camera-123/2025-12-23T10-30-00.jpg",
        )

        # Mock signal source
        mock_source = AsyncMock()
        mock_source.id = signal_source_id
        mock_source.name = "Test Camera"
        mock_source.config = {"camera_id": "camera-123"}
        mock_source.project_id = project_id
        mock_source.account_id = account_id

        # Mock feed
        mock_feed = AsyncMock()
        mock_feed.id = feed_id
        mock_feed.last_capture_at = captured_at

        # Mock repositories
        mock_source_repo = AsyncMock()
        mock_source_repo.get_by_id.return_value = mock_source

        mock_feed_repo = AsyncMock()
        mock_feed_repo.get_by_source_id.return_value = mock_feed
        mock_feed_repo.update_last_capture.return_value = mock_feed

        mock_account_repo = AsyncMock()
        mock_account = AsyncMock()
        mock_account.name = "Test Account"
        mock_account_repo.get_account_by_id.return_value = mock_account

        mock_project_repo = AsyncMock()
        mock_project = AsyncMock()
        mock_project.name = "Test Project"
        mock_project_repo.get_project.return_value = mock_project

        mock_session = AsyncMock()

        with (
            patch(
                "api.routes.internal.monitoring.SignalSourceRepositoryAsync",
                return_value=mock_source_repo,
            ),
            patch(
                "api.routes.internal.monitoring.SignalFeedRepositoryAsync",
                return_value=mock_feed_repo,
            ),
            patch(
                "api.routes.internal.monitoring.AccountRepositoryAsync",
                return_value=mock_account_repo,
            ),
            patch(
                "api.routes.internal.monitoring.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "api.routes.internal.monitoring._generate_presigned_url_safe",
                return_value="https://presigned-url.com",
            ),
            patch("api.routes.internal.monitoring.increment_counter") as mock_counter,
        ):
            result = await record_capture(request, mock_session)

            # Verify success
            assert result.success is True
            assert result.signal_source_id == signal_source_id
            assert result.feed_id == feed_id

            # Verify metric was emitted (no high-cardinality tags)
            mock_counter.assert_called_once_with("monitoring.camera.feed.updated")

            # Verify feed was updated
            mock_feed_repo.update_last_capture.assert_awaited_once_with(
                feed_id, captured_at, request.capture_url
            )

    @pytest.mark.asyncio
    async def test_record_capture_metrics_failure_doesnt_break_flow(self):
        """Test that capture recording works normally with OTel metrics (never raise)."""
        signal_source_id = uuid.uuid4()
        feed_id = uuid.uuid4()
        captured_at = datetime.now(timezone.utc)

        request = RecordCaptureRequest(
            signal_source_id=signal_source_id,
            captured_at=captured_at,
            capture_url=None,
        )

        # Mock signal source without config (to test fallback)
        mock_source = AsyncMock()
        mock_source.id = signal_source_id
        mock_source.name = "Test Camera"
        mock_source.config = None  # No config
        mock_source.project_id = None
        mock_source.account_id = uuid.uuid4()

        # Mock feed
        mock_feed = AsyncMock()
        mock_feed.id = feed_id

        # Mock repositories
        mock_source_repo = AsyncMock()
        mock_source_repo.get_by_id.return_value = mock_source

        mock_feed_repo = AsyncMock()
        mock_feed_repo.get_by_source_id.return_value = mock_feed
        mock_feed_repo.update_last_capture.return_value = mock_feed

        mock_account_repo = AsyncMock()
        mock_account = AsyncMock()
        mock_account.name = "Test Account"
        mock_account_repo.get_account_by_id.return_value = mock_account

        mock_project_repo = AsyncMock()
        mock_project_repo.get_project.return_value = None

        mock_session = AsyncMock()

        with (
            patch(
                "api.routes.internal.monitoring.SignalSourceRepositoryAsync",
                return_value=mock_source_repo,
            ),
            patch(
                "api.routes.internal.monitoring.SignalFeedRepositoryAsync",
                return_value=mock_feed_repo,
            ),
            patch(
                "api.routes.internal.monitoring.AccountRepositoryAsync",
                return_value=mock_account_repo,
            ),
            patch(
                "api.routes.internal.monitoring.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "api.routes.internal.monitoring._generate_presigned_url_safe",
                return_value=None,
            ),
            patch("api.routes.internal.monitoring.increment_counter") as mock_counter,
        ):
            result = await record_capture(request, mock_session)

            # Verify success (OTel metrics never raise exceptions)
            assert result.success is True
            assert result.signal_source_id == signal_source_id
            assert result.feed_id == feed_id

            # Verify metric was called
            mock_counter.assert_called_once_with("monitoring.camera.feed.updated")

            # Verify feed was updated
            mock_feed_repo.update_last_capture.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_capture_no_feed_found(self):
        """Test record_capture when no feed exists for signal source."""
        signal_source_id = uuid.uuid4()
        captured_at = datetime.now(timezone.utc)

        request = RecordCaptureRequest(
            signal_source_id=signal_source_id,
            captured_at=captured_at,
            capture_url=None,
        )

        # Mock signal source
        mock_source = AsyncMock()
        mock_source.id = signal_source_id
        mock_source.name = "Test Camera"
        mock_source.config = {"camera_id": "camera-123"}
        mock_source.project_id = uuid.uuid4()
        mock_source.account_id = uuid.uuid4()

        # Mock repositories
        mock_source_repo = AsyncMock()
        mock_source_repo.get_by_id.return_value = mock_source

        mock_feed_repo = AsyncMock()
        mock_feed_repo.get_by_source_id.return_value = None  # No feed found

        mock_account_repo = AsyncMock()
        mock_account = AsyncMock()
        mock_account.name = "Test Account"
        mock_account_repo.get_account_by_id.return_value = mock_account

        mock_project_repo = AsyncMock()
        mock_project = AsyncMock()
        mock_project.name = "Test Project"
        mock_project_repo.get_project.return_value = mock_project

        mock_session = AsyncMock()

        with (
            patch(
                "api.routes.internal.monitoring.SignalSourceRepositoryAsync",
                return_value=mock_source_repo,
            ),
            patch(
                "api.routes.internal.monitoring.SignalFeedRepositoryAsync",
                return_value=mock_feed_repo,
            ),
            patch(
                "api.routes.internal.monitoring.AccountRepositoryAsync",
                return_value=mock_account_repo,
            ),
            patch(
                "api.routes.internal.monitoring.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch("api.routes.internal.monitoring.increment_counter") as mock_counter,
        ):
            result = await record_capture(request, mock_session)

            # Verify failure response
            assert result.success is False
            assert result.signal_source_id == signal_source_id
            assert result.feed_id is None

            # Verify no metric was emitted (feed doesn't exist)
            mock_counter.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_capture_exception_handling(self):
        """Test record_capture handles exceptions correctly and emits error metric."""
        signal_source_id = uuid.uuid4()

        request = RecordCaptureRequest(
            signal_source_id=signal_source_id,
            captured_at=None,
            capture_url=None,
        )

        mock_session = AsyncMock()

        with (
            patch(
                "api.routes.internal.monitoring.SignalSourceRepositoryAsync",
                side_effect=Exception("Database error"),
            ),
            patch("api.routes.internal.monitoring.increment_counter") as mock_counter,
            patch("api.routes.internal.monitoring.logger") as mock_logger,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await record_capture(request, mock_session)

            # Verify 500 error
            assert exc_info.value.status_code == 500
            assert "Failed to record capture" in exc_info.value.detail

            # Verify error metric was emitted (only error_type tag, no camera_id)
            mock_counter.assert_called_once_with(
                "monitoring.camera.feed.error",
                attributes={"error_type": "Exception"},
            )

            # Verify error was logged
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_capture_exception_with_source_context(self):
        """Test error metric emits only error_type tag (no high-cardinality camera_id)."""
        signal_source_id = uuid.uuid4()

        request = RecordCaptureRequest(
            signal_source_id=signal_source_id,
            captured_at=None,
            capture_url=None,
        )

        # Mock source with camera_id
        mock_source = AsyncMock()
        mock_source.id = signal_source_id
        mock_source.config = {"camera_id": "camera-123"}

        mock_source_repo = AsyncMock()
        mock_source_repo.get_by_id.return_value = mock_source

        mock_session = AsyncMock()

        with (
            patch(
                "api.routes.internal.monitoring.SignalSourceRepositoryAsync",
                return_value=mock_source_repo,
            ),
            patch(
                "api.routes.internal.monitoring.AccountRepositoryAsync",
                side_effect=RuntimeError("Account lookup failed"),
            ),
            patch("api.routes.internal.monitoring.increment_counter") as mock_counter,
            patch("api.routes.internal.monitoring.logger") as mock_logger,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await record_capture(request, mock_session)

            # Verify 500 error
            assert exc_info.value.status_code == 500

            # Verify error metric was emitted (only error_type tag, no camera_id)
            mock_counter.assert_called_once_with(
                "monitoring.camera.feed.error",
                attributes={"error_type": "RuntimeError"},
            )

            # Verify error was logged
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_capture_error_metric_failure_doesnt_break(self):
        """Test that error handling works correctly with OTel metrics (never raise)."""
        signal_source_id = uuid.uuid4()

        request = RecordCaptureRequest(
            signal_source_id=signal_source_id,
            captured_at=None,
            capture_url=None,
        )

        mock_session = AsyncMock()

        with (
            patch(
                "api.routes.internal.monitoring.SignalSourceRepositoryAsync",
                side_effect=Exception("Database error"),
            ),
            patch("api.routes.internal.monitoring.increment_counter") as mock_counter,
            patch("api.routes.internal.monitoring.logger") as mock_logger,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await record_capture(request, mock_session)

            # Verify 500 error is raised (OTel metrics never raise exceptions)
            assert exc_info.value.status_code == 500
            assert "Failed to record capture" in exc_info.value.detail

            # Verify metric was called
            mock_counter.assert_called_once_with(
                "monitoring.camera.feed.error",
                attributes={"error_type": "Exception"},
            )

            # Verify original error was logged
            mock_logger.error.assert_called_once()
