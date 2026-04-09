"""Tests for monitoring service delete_config.

Verifies that delete_config:
- Uses bulk SQL delete for runs (delete_runs_by_config_id)
- Schedules S3 cleanup as a background task instead of blocking
- Returns False when project or config not found
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


class TestDeleteConfig:
    """Unit tests for monitoring_service.delete_config."""

    @pytest.mark.asyncio
    async def test_delete_config_bulk_deletes_runs(
        self, mock_session: AsyncMock
    ) -> None:
        """Runs are deleted via bulk delete_runs_by_config_id, not fetched individually."""
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = None

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        mock_config_repo = MagicMock()
        mock_config_repo.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.delete = AsyncMock(return_value=True)

        mock_run_repo = MagicMock()
        mock_run_repo.delete_runs_by_config_id = AsyncMock(return_value=5)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync",
                return_value=mock_config_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import delete_config

            result = await delete_config(
                session=mock_session,
                project_id=project_id,
                config_id=config_id,
            )

        assert result is True
        mock_run_repo.delete_runs_by_config_id.assert_called_once_with(config_id)

    @pytest.mark.asyncio
    async def test_delete_config_s3_cleanup_is_background(
        self, mock_session: AsyncMock
    ) -> None:
        """S3 cleanup is scheduled as background task, not awaited inline."""
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.rules = {
            "reference_images": [
                {"url": "s3://bucket/img1.jpg"},
                {"url": "s3://bucket/img2.jpg"},
            ]
        }

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        mock_config_repo = MagicMock()
        mock_config_repo.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.delete = AsyncMock(return_value=True)

        mock_run_repo = MagicMock()
        mock_run_repo.delete_runs_by_config_id = AsyncMock(return_value=0)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync",
                return_value=mock_config_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
            patch(
                "services.monitoring_service._implementation._schedule_background_task"
            ) as mock_schedule,
        ):
            from services.monitoring_service._implementation import delete_config

            result = await delete_config(
                session=mock_session,
                project_id=project_id,
                config_id=config_id,
            )

        assert result is True
        mock_schedule.assert_called_once()
        call_args = mock_schedule.call_args
        assert call_args[1]["name"] == f"cleanup-images-config-{config_id}"

    @pytest.mark.asyncio
    async def test_delete_config_returns_false_for_missing_project(
        self, mock_session: AsyncMock
    ) -> None:
        """Returns False when project does not exist."""
        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=None)

        with patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync",
            return_value=mock_project_repo,
        ):
            from services.monitoring_service._implementation import delete_config

            result = await delete_config(
                session=mock_session,
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_config_returns_false_for_missing_config(
        self, mock_session: AsyncMock
    ) -> None:
        """Returns False when config does not exist."""
        mock_project = MagicMock()
        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        mock_config_repo = MagicMock()
        mock_config_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync",
                return_value=mock_config_repo,
            ),
        ):
            from services.monitoring_service._implementation import delete_config

            result = await delete_config(
                session=mock_session,
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
            )

        assert result is False
