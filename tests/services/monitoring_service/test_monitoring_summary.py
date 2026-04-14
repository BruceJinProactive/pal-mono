"""Tests for monitoring service get_monitoring_summary.

Verifies that get_monitoring_summary:
- Returns per-tag health summaries with correct fail_rate computation
- Derives total_tags from query result length
- Includes project_name from project lookup
- Forwards start_date/end_date to repository
- Defaults to today when no time range provided
- Raises ValueError when project not found
- Returns empty tags list when no tags/runs exist
- Handles edge cases: single run, all errors, high volume
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_tag_row(
    tag: str, total_runs: int, pass_count: int, fail_count: int, error_count: int
) -> MagicMock:
    """Create a mock row matching the repository return type."""
    row = MagicMock()
    row.tag = tag
    row.total_runs = total_runs
    row.pass_count = pass_count
    row.fail_count = fail_count
    row.error_count = error_count
    return row


class TestGetMonitoringSummary:
    """Unit tests for monitoring_service.get_monitoring_summary."""

    @pytest.mark.asyncio
    async def test_mixed_statuses(self, mock_session: AsyncMock) -> None:
        """Tags with different fail rates get correct status labels."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Irvine Downtown"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Food consistency", 100, 20, 60, 20),  # 60% fail -> critical
            _make_tag_row("Wait time", 100, 40, 30, 30),  # 30% fail -> warning
            _make_tag_row(
                "Staffing compliance", 100, 80, 10, 10
            ),  # 10% fail -> healthy
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.project_id == project_id
        assert result.project_name == "Irvine Downtown"
        assert result.total_tags == 3
        assert len(result.tags) == 3

        assert result.tags[0].tag == "Food consistency"
        assert result.tags[0].fail_rate == 0.6

        assert result.tags[1].tag == "Wait time"
        assert result.tags[1].fail_rate == 0.3

        assert result.tags[2].tag == "Staffing compliance"
        assert result.tags[2].fail_rate == 0.1

    @pytest.mark.asyncio
    async def test_all_healthy(self, mock_session: AsyncMock) -> None:
        """All tags healthy when fail rates are below 25%."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Test Location"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Cleanliness", 200, 190, 5, 5),  # 2.5% fail -> healthy
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.total_tags == 1
        assert result.tags[0].fail_rate == 0.025

    @pytest.mark.asyncio
    async def test_no_tags(self, mock_session: AsyncMock) -> None:
        """Returns empty tags list when no configs have tags."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Empty Location"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=[])

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.total_tags == 0
        assert result.tags == []
        assert result.project_name == "Empty Location"

    @pytest.mark.asyncio
    async def test_project_not_found(self, mock_session: AsyncMock) -> None:
        """Raises ValueError when project does not exist."""
        project_id = uuid.uuid4()

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=None)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

    @pytest.mark.asyncio
    async def test_time_range_forwarded(self, mock_session: AsyncMock) -> None:
        """start_date and end_date are passed through to repository."""
        project_id = uuid.uuid4()
        start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        end = datetime(2026, 4, 14, tzinfo=timezone.utc)

        mock_project = MagicMock()
        mock_project.name = "Test Location"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=[])

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
                start_date=start,
                end_date=end,
            )

        mock_run_repo.get_summary_by_tags.assert_called_once_with(
            project_id=project_id,
            start_date=start,
            end_date=end,
        )
        assert result.start_date == start
        assert result.end_date == end

    @pytest.mark.asyncio
    async def test_zero_runs_returns_zero_fail_rate(
        self, mock_session: AsyncMock
    ) -> None:
        """Tag with zero total runs returns 0.0 fail_rate."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Zero Runs"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Empty tag", 0, 0, 0, 0),
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.tags[0].fail_rate == 0.0

    @pytest.mark.asyncio
    async def test_default_today_when_no_dates(self, mock_session: AsyncMock) -> None:
        """Defaults to today (midnight-to-midnight UTC) when no dates provided."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Default Date"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=[])

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        call_kwargs = mock_run_repo.get_summary_by_tags.call_args.kwargs
        today = datetime.now(timezone.utc).date()
        expected_start = datetime(
            today.year, today.month, today.day, tzinfo=timezone.utc
        )
        expected_end = expected_start + timedelta(days=1)

        assert call_kwargs["start_date"] == expected_start
        assert call_kwargs["end_date"] == expected_end
        assert result.start_date == expected_start
        assert result.end_date == expected_end

    @pytest.mark.asyncio
    async def test_single_run_per_tag(self, mock_session: AsyncMock) -> None:
        """Correct fail_rate when a tag has only one run."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Single Run"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Only pass", 1, 1, 0, 0),
            _make_tag_row("Only fail", 1, 0, 1, 0),
            _make_tag_row("Only error", 1, 0, 0, 1),
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.tags[0].fail_rate == 0.0
        assert result.tags[0].pass_count == 1

        assert result.tags[1].fail_rate == 1.0
        assert result.tags[1].fail_count == 1

        assert result.tags[2].fail_rate == 0.0
        assert result.tags[2].error_count == 1

    @pytest.mark.asyncio
    async def test_all_errors_zero_fail_rate(self, mock_session: AsyncMock) -> None:
        """Tag with all errors has fail_rate 0.0 (errors are not fails)."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "All Errors"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Broken camera", 50, 0, 0, 50),
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.tags[0].fail_rate == 0.0
        assert result.tags[0].error_count == 50
        assert result.tags[0].total_runs == 50

    @pytest.mark.asyncio
    async def test_high_volume_location(self, mock_session: AsyncMock) -> None:
        """Handles realistic high-volume location (~50K runs across tags)."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "High Volume Location"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Food consistency", 12000, 3000, 7200, 1800),
            _make_tag_row("Wait time", 10000, 4000, 3500, 2500),
            _make_tag_row("Staffing compliance", 15000, 12000, 1500, 1500),
            _make_tag_row("Cleanliness", 8000, 7500, 200, 300),
            _make_tag_row("Safety", 5000, 4900, 50, 50),
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.total_tags == 5
        assert result.tags[0].fail_rate == 0.6  # 7200/12000
        assert result.tags[1].fail_rate == 0.35  # 3500/10000
        assert result.tags[2].fail_rate == 0.1  # 1500/15000
        assert result.tags[3].fail_rate == 0.025  # 200/8000
        assert result.tags[4].fail_rate == 0.01  # 50/5000

    @pytest.mark.asyncio
    async def test_fail_rate_rounding(self, mock_session: AsyncMock) -> None:
        """fail_rate is rounded to 4 decimal places."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Rounding Test"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        # 1/3 = 0.333333... should round to 0.3333
        tag_rows = [
            _make_tag_row("Repeating decimal", 3, 2, 1, 0),
        ]

        mock_run_repo = MagicMock()
        mock_run_repo.get_summary_by_tags = AsyncMock(return_value=tag_rows)

        with (
            patch(
                "services.monitoring_service._implementation.ProjectRepositoryAsync",
                return_value=mock_project_repo,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync",
                return_value=mock_run_repo,
            ),
        ):
            from services.monitoring_service._implementation import (
                get_monitoring_summary,
            )

            result = await get_monitoring_summary(
                session=mock_session,
                project_id=project_id,
            )

        assert result.tags[0].fail_rate == 0.3333
