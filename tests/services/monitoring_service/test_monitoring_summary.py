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
- Includes per-config breakdown within each tag
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_tag_row(
    tag: str,
    total_runs: int,
    pass_count: int,
    fail_count: int,
    error_count: int,
    config_id: uuid.UUID | None = None,
    config_name: str = "Default Config",
) -> MagicMock:
    """Create a mock row matching the repository return type."""
    row = MagicMock()
    row.tag = tag
    row.config_id = config_id or uuid.uuid4()
    row.config_name = config_name
    row.total_runs = total_runs
    row.pass_count = pass_count
    row.fail_count = fail_count
    row.error_count = error_count
    return row


class TestGetMonitoringSummary:
    """Unit tests for monitoring_service.get_monitoring_summary."""

    @pytest.mark.asyncio
    async def test_mixed_statuses(self, mock_session: AsyncMock) -> None:
        """Tags with different fail rates get correct fail_rate values."""
        project_id = uuid.uuid4()
        config_id_1 = uuid.uuid4()
        config_id_2 = uuid.uuid4()
        config_id_3 = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Irvine Downtown"
        mock_project.display_name = "Irvine Downtown Store"

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row(
                "Food consistency", 100, 20, 60, 20, config_id_1, "Kitchen Check"
            ),
            _make_tag_row("Wait time", 100, 40, 30, 30, config_id_2, "Line Monitor"),
            _make_tag_row(
                "Staffing compliance", 100, 80, 10, 10, config_id_3, "Staff Check"
            ),
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

        assert result["project_id"] == str(project_id)
        assert result["project_name"] == "Irvine Downtown"
        assert result["display_name"] == "Irvine Downtown Store"
        assert result["total_tags"] == 3
        assert len(result["tags"]) == 3

        assert result["tags"][0]["tag"] == "Food consistency"
        assert result["tags"][0]["fail_rate"] == 0.6
        assert len(result["tags"][0]["configs"]) == 1
        assert result["tags"][0]["configs"][0]["config_id"] == str(config_id_1)
        assert result["tags"][0]["configs"][0]["config_name"] == "Kitchen Check"

        assert result["tags"][1]["tag"] == "Wait time"
        assert result["tags"][1]["fail_rate"] == 0.3

        assert result["tags"][2]["tag"] == "Staffing compliance"
        assert result["tags"][2]["fail_rate"] == 0.1

    @pytest.mark.asyncio
    async def test_all_healthy(self, mock_session: AsyncMock) -> None:
        """All tags healthy when fail rates are below 25%."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Test Location"
        mock_project.display_name = None

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        tag_rows = [
            _make_tag_row("Cleanliness", 200, 190, 5, 5),
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

        assert result["total_tags"] == 1
        assert result["tags"][0]["fail_rate"] == 0.025

    @pytest.mark.asyncio
    async def test_no_tags(self, mock_session: AsyncMock) -> None:
        """Returns empty tags list when no configs have tags."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Empty Location"
        mock_project.display_name = None

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

        assert result["total_tags"] == 0
        assert result["tags"] == []
        assert result["project_name"] == "Empty Location"

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
        mock_project.display_name = None

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
        # Pydantic model_dump(mode="json") serializes UTC as "Z" suffix
        assert result["start_date"] == "2026-04-01T00:00:00Z"
        assert result["end_date"] == "2026-04-14T00:00:00Z"

    @pytest.mark.asyncio
    async def test_zero_runs_returns_zero_fail_rate(
        self, mock_session: AsyncMock
    ) -> None:
        """Tag with zero total runs returns 0.0 fail_rate."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Zero Runs"
        mock_project.display_name = None

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

        assert result["tags"][0]["fail_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_default_today_when_no_dates(self, mock_session: AsyncMock) -> None:
        """Defaults to today (midnight-to-midnight UTC) when no dates provided."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Default Date"
        mock_project.display_name = None

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
        # Dates are serialized via Pydantic model_dump(mode="json")
        assert result["start_date"] is not None
        assert result["end_date"] is not None

    @pytest.mark.asyncio
    async def test_single_run_per_tag(self, mock_session: AsyncMock) -> None:
        """Correct fail_rate when a tag has only one run."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Single Run"
        mock_project.display_name = None

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

        # Sorted by fail_count desc: "Only fail" (1) first, then the rest (0)
        assert result["tags"][0]["tag"] == "Only fail"
        assert result["tags"][0]["fail_rate"] == 1.0
        assert result["tags"][0]["fail_count"] == 1

        assert result["tags"][1]["tag"] == "Only pass"
        assert result["tags"][1]["fail_rate"] == 0.0
        assert result["tags"][1]["pass_count"] == 1

        assert result["tags"][2]["tag"] == "Only error"
        assert result["tags"][2]["fail_rate"] == 0.0
        assert result["tags"][2]["error_count"] == 1

    @pytest.mark.asyncio
    async def test_all_errors_zero_fail_rate(self, mock_session: AsyncMock) -> None:
        """Tag with all errors has fail_rate 0.0 (errors are not fails)."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "All Errors"
        mock_project.display_name = None

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

        assert result["tags"][0]["fail_rate"] == 0.0
        assert result["tags"][0]["error_count"] == 50
        assert result["tags"][0]["total_runs"] == 50

    @pytest.mark.asyncio
    async def test_high_volume_location(self, mock_session: AsyncMock) -> None:
        """Handles realistic high-volume location (~50K runs across tags)."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "High Volume Location"
        mock_project.display_name = None

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

        assert result["total_tags"] == 5
        assert result["tags"][0]["fail_rate"] == 0.6  # 7200/12000
        assert result["tags"][1]["fail_rate"] == 0.35  # 3500/10000
        assert result["tags"][2]["fail_rate"] == 0.1  # 1500/15000
        assert result["tags"][3]["fail_rate"] == 0.025  # 200/8000
        assert result["tags"][4]["fail_rate"] == 0.01  # 50/5000

    @pytest.mark.asyncio
    async def test_fail_rate_rounding(self, mock_session: AsyncMock) -> None:
        """fail_rate is rounded to 4 decimal places."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Rounding Test"
        mock_project.display_name = None

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

        assert result["tags"][0]["fail_rate"] == 0.3333

    @pytest.mark.asyncio
    async def test_multiple_configs_per_tag(self, mock_session: AsyncMock) -> None:
        """Multiple configs sharing a tag are aggregated at tag level with per-config breakdown."""
        project_id = uuid.uuid4()
        config_id_a = uuid.uuid4()
        config_id_b = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "Multi Config"
        mock_project.display_name = None

        mock_project_repo = MagicMock()
        mock_project_repo.get_project = AsyncMock(return_value=mock_project)

        # Two configs share the same tag "Cleanliness"
        tag_rows = [
            _make_tag_row("Cleanliness", 30, 20, 9, 1, config_id_a, "Morning Check"),
            _make_tag_row("Cleanliness", 20, 10, 9, 1, config_id_b, "Evening Check"),
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

        # Single tag with aggregated totals
        assert result["total_tags"] == 1
        tag: dict[str, Any] = result["tags"][0]
        assert tag["tag"] == "Cleanliness"
        assert tag["total_runs"] == 50  # 30 + 20
        assert tag["pass_count"] == 30  # 20 + 10
        assert tag["fail_count"] == 18  # 9 + 9
        assert tag["error_count"] == 2  # 1 + 1
        assert tag["fail_rate"] == 0.36  # 18/50

        # Per-config breakdown
        assert len(tag["configs"]) == 2
        assert tag["configs"][0]["config_id"] == str(config_id_a)
        assert tag["configs"][0]["config_name"] == "Morning Check"
        assert tag["configs"][0]["total_runs"] == 30
        assert tag["configs"][1]["config_id"] == str(config_id_b)
        assert tag["configs"][1]["config_name"] == "Evening Check"
        assert tag["configs"][1]["total_runs"] == 20
