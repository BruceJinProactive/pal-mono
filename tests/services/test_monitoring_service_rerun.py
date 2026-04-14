"""Tests for monitoring service rerun functionality.

These tests verify the rerun logic for monitoring runs, including support for
manual triggers (s3_key), automated triggers (image_url/video_url), and
proper error handling.

NOTE: These tests use extensive mocking. For full integration tests,
use Docker: docker exec -it pal-mono-api pytest tests/services/...
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_run_with_s3_key():
    """Mock monitoring run with s3_key trigger metadata (manual trigger)."""
    run = MagicMock()
    run.id = uuid.uuid4()
    run.monitoring_config_id = uuid.uuid4()
    run.trigger_metadata = {
        "s3_key": "test-bucket/test-image.jpg",
        "trigger_source": "manual_api",
    }
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.evaluation_result = {"result": "pass", "details": "Original result"}
    run.error_message = None
    return run


@pytest.fixture
def mock_config():
    """Mock monitoring configuration."""
    config = MagicMock()
    config.id = uuid.uuid4()
    config.project_id = uuid.uuid4()
    config.signal_source_id = uuid.uuid4()
    config.rules = {
        "context": "Test monitoring",
        "pass_criteria": ["Image is clear"],
        "fail_criteria": ["Image is blurry"],
    }
    return config


@pytest.fixture
def mock_image_feed():
    """Mock image signal feed."""
    feed = MagicMock()
    # Mock FeedType comparison
    feed.feed_type = MagicMock()
    feed.feed_type.__eq__ = lambda self, other: False  # Not video_stream
    return feed


# ============================================================================
# TESTS FOR rerun_monitoring_run
# ============================================================================


@pytest.mark.asyncio
async def test_rerun_with_s3_key_extracts_media_url(
    mock_session, mock_run_with_s3_key, mock_config, mock_image_feed
):
    """Test that rerun correctly extracts media URL from s3_key for manual triggers."""
    from services.monitoring_service._implementation import rerun_monitoring_run

    # Setup mocks
    mock_run_repo = AsyncMock()
    mock_run_repo.get_by_id = AsyncMock(return_value=mock_run_with_s3_key)
    mock_run_repo.update = AsyncMock(return_value=mock_run_with_s3_key)

    mock_config_repo = AsyncMock()
    mock_config_repo.get_by_id = AsyncMock(return_value=mock_config)

    mock_feed_repo = AsyncMock()
    mock_feed_repo.get_by_source_id = AsyncMock(return_value=mock_image_feed)

    with (
        patch(
            "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
            return_value=mock_run_repo,
        ),
        patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync",
            return_value=mock_config_repo,
        ),
        patch(
            "db.repositories.SignalFeedRepositoryAsync",
            return_value=mock_feed_repo,
        ),
        patch("asyncio.create_task") as mock_create_task,
    ):

        result = await rerun_monitoring_run(
            session=mock_session,
            project_id=mock_config.project_id,
            run_id=mock_run_with_s3_key.id,
        )

        # Verify result
        assert result["run_id"] == mock_run_with_s3_key.id
        assert (
            result["monitoring_config_id"] == mock_run_with_s3_key.monitoring_config_id
        )
        assert result["status"] == "processing"

        # Verify run was updated with processing status
        mock_run_repo.update.assert_called_once()
        update_args = mock_run_repo.update.call_args
        assert update_args[0][0] == mock_run_with_s3_key.id
        evaluation_result = update_args[1]["evaluation_result"]
        assert evaluation_result["result"] == "processing"
        assert evaluation_result["status"] == "rerunning"
        assert "rerun_started_at" in evaluation_result

        # Verify result/details/confidence columns are set
        assert update_args[1]["result"] == "processing"
        assert (
            update_args[1]["details"]
            == "Analysis is being rerun. Results will be updated when complete."
        )
        assert update_args[1]["confidence"] is None

        # Verify background task was spawned
        mock_create_task.assert_called_once()

        # Verify commit was called
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_rerun_with_missing_media_raises_error(
    mock_session, mock_run_with_s3_key, mock_config, mock_image_feed
):
    """Test that rerun raises ValueError when no media URL exists in trigger_metadata."""
    from services.monitoring_service._implementation import rerun_monitoring_run

    # Remove all media references
    mock_run_with_s3_key.trigger_metadata = {"trigger_source": "manual_api"}

    mock_run_repo = AsyncMock()
    mock_run_repo.get_by_id = AsyncMock(return_value=mock_run_with_s3_key)

    mock_config_repo = AsyncMock()
    mock_config_repo.get_by_id = AsyncMock(return_value=mock_config)

    mock_feed_repo = AsyncMock()
    mock_feed_repo.get_by_source_id = AsyncMock(return_value=mock_image_feed)

    with (
        patch(
            "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
            return_value=mock_run_repo,
        ),
        patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync",
            return_value=mock_config_repo,
        ),
        patch(
            "db.repositories.SignalFeedRepositoryAsync",
            return_value=mock_feed_repo,
        ),
    ):

        with pytest.raises(ValueError) as exc_info:
            await rerun_monitoring_run(
                session=mock_session,
                project_id=mock_config.project_id,
                run_id=mock_run_with_s3_key.id,
            )

        error_msg = str(exc_info.value)
        assert "No media URL found" in error_msg
        assert "image_url, video_url, and s3_key" in error_msg


@pytest.mark.asyncio
async def test_rerun_with_nonexistent_run_raises_error(mock_session):
    """Test that rerun raises ValueError when run doesn't exist."""
    from services.monitoring_service._implementation import rerun_monitoring_run

    mock_run_repo = AsyncMock()
    mock_run_repo.get_by_id = AsyncMock(return_value=None)

    with patch(
        "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
        return_value=mock_run_repo,
    ):

        with pytest.raises(ValueError) as exc_info:
            await rerun_monitoring_run(
                session=mock_session,
                project_id=uuid.uuid4(),
                run_id=uuid.uuid4(),
            )

        assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rerun_with_wrong_project_raises_error(
    mock_session, mock_run_with_s3_key, mock_config
):
    """Test that rerun raises ValueError when run doesn't belong to project."""
    from services.monitoring_service._implementation import rerun_monitoring_run

    mock_run_repo = AsyncMock()
    mock_run_repo.get_by_id = AsyncMock(return_value=mock_run_with_s3_key)

    mock_config_repo = AsyncMock()
    mock_config_repo.get_by_id = AsyncMock(return_value=mock_config)

    with (
        patch(
            "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
            return_value=mock_run_repo,
        ),
        patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync",
            return_value=mock_config_repo,
        ),
    ):

        wrong_project_id = uuid.uuid4()
        with pytest.raises(ValueError) as exc_info:
            await rerun_monitoring_run(
                session=mock_session,
                project_id=wrong_project_id,
                run_id=mock_run_with_s3_key.id,
            )

        assert "does not belong to project" in str(exc_info.value)


# ============================================================================
# TESTS FOR _rerun_monitoring_analysis_background
# ============================================================================


async def mock_get_db_async():
    """Mock async generator for database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    yield session


@pytest.mark.asyncio
async def test_background_rerun_image_success():
    """Test that background rerun successfully analyzes image and updates run."""
    from services.monitoring_service._implementation import (
        _rerun_monitoring_analysis_background,
    )

    run_id = uuid.uuid4()
    config_id = uuid.uuid4()
    media_url = "test-bucket/image.jpg"

    # Mock successful LLM response
    mock_llm_result = {
        "analysis_result": {
            "result": "pass",
            "details": "Analysis passed",
            "confidence": 0.95,
        }
    }

    mock_run_repo = AsyncMock()
    mock_run_repo.update = AsyncMock()

    with (
        patch(
            "db.get_db_async",
            mock_get_db_async,
        ),
        patch(
            "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
            return_value=mock_run_repo,
        ),
        patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            new_callable=AsyncMock,
            return_value=mock_llm_result,
        ) as mock_llm_prompt,
    ):

        await _rerun_monitoring_analysis_background(
            run_id=run_id,
            monitoring_config_id=config_id,
            media_url=media_url,
            is_video=False,
        )

        # Verify LLM was called with correct parameters
        mock_llm_prompt.assert_called_once()
        llm_call_kwargs = mock_llm_prompt.call_args[1]
        assert llm_call_kwargs["monitoring_config_id"] == config_id
        assert llm_call_kwargs["image_url"] == media_url

        # Verify run was updated with new result
        mock_run_repo.update.assert_called_once()
        update_args = mock_run_repo.update.call_args
        assert update_args[0][0] == run_id
        assert update_args[1]["evaluation_result"]["result"] == "pass"
        assert update_args[1]["error_message"] is None
        # Verify completed_at was NOT updated
        assert "completed_at" not in update_args[1]
        # Verify result/details/confidence columns are set
        assert update_args[1]["result"] == "pass"
        assert update_args[1]["details"] == "Analysis passed"
        assert update_args[1]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_background_rerun_handles_llm_exception():
    """Test that background rerun handles LLM exceptions and updates run with error."""
    from services.monitoring_service._implementation import (
        _rerun_monitoring_analysis_background,
    )

    run_id = uuid.uuid4()
    config_id = uuid.uuid4()
    media_url = "test-bucket/image.jpg"

    mock_run_repo = AsyncMock()
    mock_run_repo.update = AsyncMock()

    with (
        patch(
            "db.get_db_async",
            mock_get_db_async,
        ),
        patch(
            "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
            return_value=mock_run_repo,
        ),
        patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            new_callable=AsyncMock,
            side_effect=Exception("LLM service unavailable"),
        ),
    ):

        await _rerun_monitoring_analysis_background(
            run_id=run_id,
            monitoring_config_id=config_id,
            media_url=media_url,
            is_video=False,
        )

        # Verify run was updated with error status
        mock_run_repo.update.assert_called_once()
        error_update = mock_run_repo.update.call_args
        evaluation_result = error_update[1]["evaluation_result"]
        assert evaluation_result["result"] == "error"
        assert "Rerun failed" in evaluation_result["details"]
        assert evaluation_result["status"] == "failed"
        assert "Rerun failed" in error_update[1]["error_message"]
        # Verify result/details/confidence columns are set
        assert error_update[1]["result"] == "error"
        assert "Rerun failed" in error_update[1]["details"]
        assert error_update[1]["confidence"] is None


@pytest.mark.asyncio
async def test_background_rerun_preserves_completed_at():
    """Test that background rerun only updates evaluation_result, not completed_at."""
    from services.monitoring_service._implementation import (
        _rerun_monitoring_analysis_background,
    )

    run_id = uuid.uuid4()
    config_id = uuid.uuid4()
    media_url = "test-bucket/image.jpg"

    mock_llm_result = {
        "analysis_result": {
            "result": "pass",
            "details": "Analysis passed",
        }
    }

    mock_run_repo = AsyncMock()
    mock_run_repo.update = AsyncMock()

    with (
        patch(
            "db.get_db_async",
            mock_get_db_async,
        ),
        patch(
            "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
            return_value=mock_run_repo,
        ),
        patch(
            "services.monitoring_service._llm.generate_monitoring_llm_prompt",
            new_callable=AsyncMock,
            return_value=mock_llm_result,
        ),
    ):

        await _rerun_monitoring_analysis_background(
            run_id=run_id,
            monitoring_config_id=config_id,
            media_url=media_url,
            is_video=False,
        )

        # Verify completed_at was NOT in the update call
        update_kwargs = mock_run_repo.update.call_args[1]
        assert "completed_at" not in update_kwargs
        assert "evaluation_result" in update_kwargs
        assert "error_message" in update_kwargs
        # Verify result/details/confidence columns are included in update
        assert "result" in update_kwargs
        assert "details" in update_kwargs
        assert "confidence" in update_kwargs
