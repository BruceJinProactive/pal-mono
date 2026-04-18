"""Tests for monitoring time window filtering logic."""

from datetime import time, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from services.monitoring_service._time_window import (
    is_within_time_window,
    parse_time,
    should_skip_monitoring,
)


class TestParseTime:
    """Tests for parse_time — parsing HH:MM strings to time objects."""

    def test_valid_time_morning(self):
        """Should parse '06:00' to time(6, 0)."""
        result = parse_time("06:00")
        assert result == time(6, 0)

    def test_valid_time_evening(self):
        """Should parse '22:30' to time(22, 30)."""
        result = parse_time("22:30")
        assert result == time(22, 30)

    def test_valid_time_midnight(self):
        """Should parse '00:00' to time(0, 0)."""
        result = parse_time("00:00")
        assert result == time(0, 0)

    def test_valid_time_end_of_day(self):
        """Should parse '23:59' to time(23, 59)."""
        result = parse_time("23:59")
        assert result == time(23, 59)

    def test_invalid_hour_out_of_range(self):
        """Should raise ValueError for hour > 23."""
        with pytest.raises(ValueError):
            parse_time("25:00")

    def test_invalid_non_numeric(self):
        """Should raise ValueError for non-numeric input."""
        with pytest.raises(ValueError):
            parse_time("abc")

    def test_invalid_too_many_parts(self):
        """Should raise ValueError for HH:MM:SS format."""
        with pytest.raises(ValueError):
            parse_time("6:00:00")

    def test_invalid_single_component(self):
        """Should raise ValueError for single number without colon."""
        with pytest.raises(ValueError):
            parse_time("06")

    def test_invalid_empty_string(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError):
            parse_time("")


class TestIsWithinTimeWindow:
    """Tests for is_within_time_window — pure time-in-range checking."""

    def test_normal_window_inside(self):
        """Should return True when time is within a normal daytime window."""
        assert is_within_time_window(time(10, 0), time(6, 0), time(22, 0)) is True

    def test_normal_window_outside(self):
        """Should return False when time is outside a normal daytime window."""
        assert is_within_time_window(time(23, 0), time(6, 0), time(22, 0)) is False

    def test_normal_window_at_start_boundary(self):
        """Should return True when time equals window start (inclusive)."""
        assert is_within_time_window(time(6, 0), time(6, 0), time(22, 0)) is True

    def test_normal_window_at_end_boundary(self):
        """Should return True when time equals window end (inclusive)."""
        assert is_within_time_window(time(22, 0), time(6, 0), time(22, 0)) is True

    def test_overnight_window_after_midnight(self):
        """Should return True when inside overnight window after midnight."""
        assert is_within_time_window(time(1, 0), time(22, 0), time(2, 0)) is True

    def test_overnight_window_before_midnight(self):
        """Should return True when inside overnight window before midnight."""
        assert is_within_time_window(time(23, 0), time(22, 0), time(2, 0)) is True

    def test_overnight_window_outside_during_day(self):
        """Should return False when outside overnight window during daytime."""
        assert is_within_time_window(time(10, 0), time(22, 0), time(2, 0)) is False

    def test_equal_start_and_end(self):
        """Should return True when start equals end and time matches exactly."""
        assert is_within_time_window(time(12, 0), time(12, 0), time(12, 0)) is True


class TestShouldSkipMonitoring:
    """Tests for should_skip_monitoring — full skip decision with DB lookup."""

    @pytest.mark.asyncio
    async def test_no_config_returns_false(self):
        """Should not skip when time_window_config is None."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")

        should_skip, reason = await should_skip_monitoring(session, project_id, None)
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_empty_config_returns_false(self):
        """Should not skip when time_window_config is empty dict."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")

        should_skip, reason = await should_skip_monitoring(session, project_id, {})
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_disabled_config_returns_false(self):
        """Should not skip when time window is disabled."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        config = {"enabled": False, "start_time": "06:00", "end_time": "22:00"}

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_missing_times_fail_open(self, mocker):
        """Should not skip (fail-open) when start/end times are missing."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        config = {"enabled": True}

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_project_not_found_fail_open(self, mocker):
        """Should not skip (fail-open) when project is not found in DB."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        config = {"enabled": True, "start_time": "06:00", "end_time": "22:00"}

        mock_repo = mocker.patch(
            "services.monitoring_service._time_window.ProjectRepositoryAsync"
        )
        mock_repo.return_value.get_project = AsyncMock(return_value=None)

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_invalid_timezone_fail_open(self, mocker):
        """Should not skip (fail-open) when project has invalid timezone."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        config = {"enabled": True, "start_time": "06:00", "end_time": "22:00"}

        mock_project = MagicMock()
        mock_project.timezone = "Invalid/Timezone_XYZ"

        mock_repo = mocker.patch(
            "services.monitoring_service._time_window.ProjectRepositoryAsync"
        )
        mock_repo.return_value.get_project = AsyncMock(return_value=mock_project)

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_within_time_window_no_skip(self, mocker):
        """Should not skip when current time is within the configured window."""
        from datetime import datetime

        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        config = {"enabled": True, "start_time": "06:00", "end_time": "22:00"}

        mock_project = MagicMock()
        mock_project.timezone = "UTC"

        mock_repo = mocker.patch(
            "services.monitoring_service._time_window.ProjectRepositoryAsync"
        )
        mock_repo.return_value.get_project = AsyncMock(return_value=mock_project)

        # Mock datetime.now to return a time inside the window
        fixed_now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        mocker.patch(
            "services.monitoring_service._time_window.datetime",
            wraps=datetime,
        )
        mocker.patch(
            "services.monitoring_service._time_window.datetime.now",
            return_value=fixed_now,
        )

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_outside_time_window_skip(self, mocker):
        """Should skip with reason when current time is outside the window."""
        from datetime import datetime

        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        # Use a very narrow window that cannot contain the current time
        # e.g., 00:00-00:01 — if it's not exactly midnight, this will skip
        # Instead, mock datetime.now to control the time
        config = {"enabled": True, "start_time": "03:00", "end_time": "03:01"}

        mock_project = MagicMock()
        mock_project.timezone = "UTC"

        mock_repo = mocker.patch(
            "services.monitoring_service._time_window.ProjectRepositoryAsync"
        )
        mock_repo.return_value.get_project = AsyncMock(return_value=mock_project)

        # Mock datetime.now to return a time outside the window
        fixed_now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        mocker.patch(
            "services.monitoring_service._time_window.datetime",
            wraps=datetime,
        )
        mocker.patch(
            "services.monitoring_service._time_window.datetime.now",
            return_value=fixed_now,
        )

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is True
        assert reason is not None
        assert "Outside monitoring time window" in reason

    @pytest.mark.asyncio
    async def test_invalid_time_format_fail_open(self):
        """Should not skip (fail-open) when time format is invalid."""
        session = AsyncMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        config = {"enabled": True, "start_time": "invalid", "end_time": "also_invalid"}

        should_skip, reason = await should_skip_monitoring(session, project_id, config)
        assert should_skip is False
        assert reason is None
