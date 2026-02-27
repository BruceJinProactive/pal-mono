"""Tests for regenerate_executions service function."""

import uuid
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from services.routine_execution_service._implementation import regenerate_executions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = "services.routine_execution_service._implementation"


def _make_schedule(**overrides) -> MagicMock:
    schedule = MagicMock()
    schedule.id = overrides.get("id", uuid.uuid4())
    schedule.routine_id = overrides.get("routine_id", uuid.uuid4())
    schedule.frequency.value = overrides.get("frequency", "daily")
    schedule.start_time = overrides.get("start_time", time(9, 0))
    schedule.end_time = overrides.get("end_time", time(17, 0))
    schedule.timezone = overrides.get("timezone", "America/Los_Angeles")
    schedule.days_of_week = overrides.get("days_of_week", None)
    schedule.day_of_month = overrides.get("day_of_month", None)
    schedule.effective_from = overrides.get("effective_from", None)
    schedule.effective_until = overrides.get("effective_until", None)
    return schedule


def _make_execution(**overrides) -> MagicMock:
    execution = MagicMock()
    execution.id = overrides.get("id", uuid.uuid4())
    execution.schedule_id = overrides.get("schedule_id", uuid.uuid4())
    execution.scheduled_start = overrides.get(
        "scheduled_start", datetime(2026, 2, 27, 17, 0, tzinfo=timezone.utc)
    )
    execution.scheduled_end = overrides.get(
        "scheduled_end", datetime(2026, 2, 28, 1, 0, tzinfo=timezone.utc)
    )
    return execution


def _patch_repos(
    schedule: MagicMock | None,
    todays_pending: list[MagicMock] | None = None,
    future_pending: list[MagicMock] | None = None,
):
    """Patch RoutineScheduleRepositoryAsync and RoutineExecutionRepositoryAsync."""
    schedule_repo = AsyncMock()
    schedule_repo.get_schedule_by_id.return_value = schedule

    execution_repo = AsyncMock()
    execution_repo.find_todays_pending_executions.return_value = todays_pending or []
    execution_repo.find_pending_executions_from.return_value = future_pending or []
    execution_repo.update_execution.return_value = MagicMock()
    execution_repo.create_execution.return_value = MagicMock(id=uuid.uuid4())

    return (
        patch(
            f"{_BASE}.RoutineScheduleRepositoryAsync",
            return_value=schedule_repo,
        ),
        patch(
            f"{_BASE}.RoutineExecutionRepositoryAsync",
            return_value=execution_repo,
        ),
        schedule_repo,
        execution_repo,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegenerateExecutionsScheduleNotFound:
    """Schedule not found -> 404."""

    @pytest.mark.asyncio
    async def test_returns_404(self) -> None:
        session = AsyncMock()
        sched_patch, exec_patch, _, _ = _patch_repos(schedule=None)

        with sched_patch, exec_patch:
            with pytest.raises(HTTPException) as exc_info:
                await regenerate_executions(uuid.uuid4(), session)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


class TestRegenerateExecutionsInvalidTimezone:
    """Invalid timezone on schedule -> 422."""

    @pytest.mark.asyncio
    async def test_returns_422(self) -> None:
        schedule = _make_schedule(timezone="Invalid/Timezone")
        session = AsyncMock()
        sched_patch, exec_patch, _, _ = _patch_repos(schedule=schedule)

        with sched_patch, exec_patch:
            with pytest.raises(HTTPException) as exc_info:
                await regenerate_executions(schedule.id, session)

        assert exc_info.value.status_code == 422
        assert "invalid timezone" in exc_info.value.detail.lower()


class TestRegenerateExecutionsUpdatesToday:
    """Today's pending executions are updated in place."""

    @pytest.mark.asyncio
    async def test_updates_today_execution(self) -> None:
        tz = ZoneInfo("America/Los_Angeles")
        frozen_now = datetime(2026, 3, 15, 10, 30, tzinfo=tz)

        schedule = _make_schedule(start_time=time(10, 0), end_time=time(18, 0))
        today_exec = _make_execution(id=uuid.uuid4(), schedule_id=schedule.id)

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
            patch(f"{_BASE}.datetime", wraps=datetime) as mock_dt,
        ):
            mock_dt.now.return_value = frozen_now
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_updated == 1
        exec_repo.update_execution.assert_awaited_once()
        call_kwargs = exec_repo.update_execution.call_args.kwargs
        assert call_kwargs["execution_id"] == today_exec.id
        # Verify exact computed times
        expected_start = datetime.combine(frozen_now.date(), time(10, 0), tzinfo=tz)
        expected_end = datetime.combine(frozen_now.date(), time(18, 0), tzinfo=tz)
        assert call_kwargs["scheduled_start"] == expected_start
        assert call_kwargs["scheduled_end"] == expected_end

    @pytest.mark.asyncio
    async def test_no_today_executions(self) -> None:
        schedule = _make_schedule()

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_updated == 0
        exec_repo.update_execution.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_failure_not_counted(self) -> None:
        """When update_execution returns None, executions_updated should be 0."""
        schedule = _make_schedule(start_time=time(10, 0), end_time=time(18, 0))
        today_exec = _make_execution(id=uuid.uuid4(), schedule_id=schedule.id)

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
        )
        # Simulate update failure
        exec_repo.update_execution.return_value = None

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_updated == 0
        exec_repo.update_execution.assert_awaited_once()


class TestRegenerateExecutionsDeletesFuture:
    """Future pending executions are deleted."""

    @pytest.mark.asyncio
    async def test_deletes_future_executions(self) -> None:
        schedule = _make_schedule()
        future_exec_1 = _make_execution()
        future_exec_2 = _make_execution()

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            future_pending=[future_exec_1, future_exec_2],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_deleted == 2
        assert session.delete.await_count == 2


class TestRegenerateExecutionsGeneratesFuture:
    """New executions are generated from tomorrow."""

    @pytest.mark.asyncio
    async def test_creates_new_executions(self) -> None:
        schedule = _make_schedule()
        tz = ZoneInfo("America/Los_Angeles")
        tomorrow = datetime.now(tz).date() + timedelta(days=1)

        fake_windows = [
            (
                datetime.combine(tomorrow, time(9, 0), tzinfo=tz),
                datetime.combine(tomorrow, time(17, 0), tzinfo=tz),
            ),
            (
                datetime.combine(tomorrow + timedelta(days=1), time(9, 0), tzinfo=tz),
                datetime.combine(tomorrow + timedelta(days=1), time(17, 0), tzinfo=tz),
            ),
        ]

        sched_patch, exec_patch, _, exec_repo = _patch_repos(schedule=schedule)

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=fake_windows,
            ),
        ):
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_created == 2
        assert exec_repo.create_execution.await_count == 2


class TestRegenerateExecutionsAtomic:
    """Commit is called exactly once."""

    @pytest.mark.asyncio
    async def test_single_commit(self) -> None:
        schedule = _make_schedule()
        today_exec = _make_execution()
        future_exec = _make_execution()

        sched_patch, exec_patch, _, _ = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
            future_pending=[future_exec],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            await regenerate_executions(schedule.id, session)

        session.commit.assert_awaited_once()


class TestRegenerateExecutionsTimezoneHandling:
    """Timezone boundaries are computed correctly."""

    @pytest.mark.asyncio
    async def test_uses_schedule_timezone(self) -> None:
        schedule = _make_schedule(
            timezone="America/New_York",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )

        sched_patch, exec_patch, _, exec_repo = _patch_repos(schedule=schedule)

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            await regenerate_executions(schedule.id, session)

        # Verify find_todays_pending_executions was called with UTC bounds
        call_kwargs = exec_repo.find_todays_pending_executions.call_args.kwargs
        today_start_utc = call_kwargs["today_start_utc"]
        today_end_utc = call_kwargs["today_end_utc"]

        # Both should be timezone-aware UTC
        assert today_start_utc.tzinfo is not None
        assert today_end_utc.tzinfo is not None

        # End should be exactly 1 day after start
        assert today_end_utc - today_start_utc == timedelta(days=1)

    @pytest.mark.asyncio
    async def test_overnight_window(self) -> None:
        """end_time < start_time: scheduled_end should be next day."""
        schedule = _make_schedule(
            start_time=time(22, 0),
            end_time=time(6, 0),
        )
        today_exec = _make_execution()

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            await regenerate_executions(schedule.id, session)

        call_kwargs = exec_repo.update_execution.call_args.kwargs
        start = call_kwargs["scheduled_start"]
        end = call_kwargs["scheduled_end"]

        # For overnight window, end should be next day
        assert end.date() == start.date() + timedelta(days=1)

    @pytest.mark.asyncio
    async def test_midnight_start_time(self) -> None:
        """start_time=00:00 should not break day boundary calculation."""
        tz = ZoneInfo("America/Los_Angeles")
        frozen_now = datetime(2026, 3, 15, 10, 0, tzinfo=tz)

        schedule = _make_schedule(
            start_time=time(0, 0),
            end_time=time(8, 0),
        )
        today_exec = _make_execution()

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
            patch(f"{_BASE}.datetime", wraps=datetime) as mock_dt,
        ):
            mock_dt.now.return_value = frozen_now
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_updated == 1
        call_kwargs = exec_repo.update_execution.call_args.kwargs
        expected_start = datetime.combine(frozen_now.date(), time(0, 0), tzinfo=tz)
        expected_end = datetime.combine(frozen_now.date(), time(8, 0), tzinfo=tz)
        assert call_kwargs["scheduled_start"] == expected_start
        assert call_kwargs["scheduled_end"] == expected_end
        # Same day — end_time >= start_time so no overnight shift
        assert (
            call_kwargs["scheduled_end"].date() == call_kwargs["scheduled_start"].date()
        )

    @pytest.mark.asyncio
    async def test_noon_start_time(self) -> None:
        """Changing schedule to start_time=12:00 produces correct window."""
        tz = ZoneInfo("America/Los_Angeles")
        frozen_now = datetime(2026, 3, 15, 14, 0, tzinfo=tz)

        schedule = _make_schedule(
            start_time=time(12, 0),
            end_time=time(20, 0),
        )
        today_exec = _make_execution()

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
            patch(f"{_BASE}.datetime", wraps=datetime) as mock_dt,
        ):
            mock_dt.now.return_value = frozen_now
            result = await regenerate_executions(schedule.id, session)

        assert result.executions_updated == 1
        call_kwargs = exec_repo.update_execution.call_args.kwargs
        assert call_kwargs["scheduled_start"] == datetime.combine(
            frozen_now.date(), time(12, 0), tzinfo=tz
        )
        assert call_kwargs["scheduled_end"] == datetime.combine(
            frozen_now.date(), time(20, 0), tzinfo=tz
        )

    @pytest.mark.asyncio
    async def test_end_time_equals_start_time(self) -> None:
        """When end_time == start_time, end_time is NOT < start_time, so same day."""
        tz = ZoneInfo("America/Los_Angeles")
        frozen_now = datetime(2026, 3, 15, 14, 0, tzinfo=tz)

        schedule = _make_schedule(
            start_time=time(12, 0),
            end_time=time(12, 0),
        )
        today_exec = _make_execution()

        sched_patch, exec_patch, _, exec_repo = _patch_repos(
            schedule=schedule,
            todays_pending=[today_exec],
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
            patch(f"{_BASE}.datetime", wraps=datetime) as mock_dt,
        ):
            mock_dt.now.return_value = frozen_now
            await regenerate_executions(schedule.id, session)

        call_kwargs = exec_repo.update_execution.call_args.kwargs
        # end_time == start_time: not < so same-day, both are 12:00
        assert (
            call_kwargs["scheduled_start"].date() == call_kwargs["scheduled_end"].date()
        )
        assert call_kwargs["scheduled_start"].time() == time(12, 0)
        assert call_kwargs["scheduled_end"].time() == time(12, 0)

    @pytest.mark.asyncio
    async def test_future_deletion_uses_inclusive_boundary(self) -> None:
        """find_pending_executions_from is called with tomorrow_start_utc (>= boundary)."""
        schedule = _make_schedule(timezone="US/Eastern")

        sched_patch, exec_patch, _, exec_repo = _patch_repos(schedule=schedule)

        session = AsyncMock()

        # Freeze "now" so test and production code agree on which day it is
        tz = ZoneInfo("US/Eastern")
        frozen_now = datetime(2026, 2, 27, 14, 30, 0, tzinfo=tz)

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
            patch(
                f"{_BASE}.datetime",
                wraps=datetime,
            ) as mock_dt,
        ):
            mock_dt.now.return_value = frozen_now
            await regenerate_executions(schedule.id, session)

        # Verify find_pending_executions_from was called (not find_executions_for_deletion)
        exec_repo.find_pending_executions_from.assert_awaited_once()
        call_kwargs = exec_repo.find_pending_executions_from.call_args.kwargs
        from_utc = call_kwargs["from_utc"]

        # from_utc should be start of tomorrow in the schedule's timezone
        expected_tomorrow_start = datetime.combine(
            frozen_now.date() + timedelta(days=1), time.min, tzinfo=tz
        ).astimezone(ZoneInfo("UTC"))

        assert from_utc == expected_tomorrow_start


class TestRegenerateExecutionsResponse:
    """Response contains correct counts."""

    @pytest.mark.asyncio
    async def test_response_counts(self) -> None:
        schedule = _make_schedule()
        today_execs = [_make_execution(), _make_execution()]
        future_execs = [_make_execution()]

        tz = ZoneInfo("America/Los_Angeles")
        tomorrow = datetime.now(tz).date() + timedelta(days=1)
        fake_window = [
            (
                datetime.combine(tomorrow, time(9, 0), tzinfo=tz),
                datetime.combine(tomorrow, time(17, 0), tzinfo=tz),
            ),
        ]

        sched_patch, exec_patch, _, _ = _patch_repos(
            schedule=schedule,
            todays_pending=today_execs,
            future_pending=future_execs,
        )

        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=fake_window,
            ),
        ):
            result = await regenerate_executions(schedule.id, session)

        assert result.schedule_id == schedule.id
        assert result.executions_updated == 2
        assert result.executions_deleted == 1
        assert result.executions_created == 1


class TestRegenerateExecutionsFacade:
    """Ensure the public facade delegates to the implementation."""

    @pytest.mark.asyncio
    async def test_facade_delegates(self) -> None:
        from services.routine_execution_service import (
            regenerate_executions as facade_fn,
        )

        schedule = _make_schedule()
        sched_patch, exec_patch, _, _ = _patch_repos(schedule=schedule)
        session = AsyncMock()

        with (
            sched_patch,
            exec_patch,
            patch(
                "services.routine_service._schedule_calculator.calculate_next_executions",
                return_value=[],
            ),
        ):
            result = await facade_fn(schedule.id, session)

        assert result.schedule_id == schedule.id
