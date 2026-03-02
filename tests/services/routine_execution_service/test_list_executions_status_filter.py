"""Tests for list_executions status_filter with pending→missed remapping."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.tables.types import ExecutionStatus, RoutineCategory
from services.routine_execution_service._implementation import list_executions

_BASE = "services.routine_execution_service._implementation"


def _make_execution(
    *,
    status: ExecutionStatus = ExecutionStatus.pending,
    scheduled_end: datetime,
) -> MagicMock:
    execution = MagicMock()
    execution.id = uuid.uuid4()
    execution.routine_id = uuid.uuid4()
    execution.schedule_id = uuid.uuid4()
    execution.scheduled_start = scheduled_end - timedelta(hours=1)
    execution.scheduled_end = scheduled_end
    execution.status = status
    execution.assigned_user_id = None
    execution.created_at = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
    execution.updated_at = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
    return execution


def _make_routine(routine_id: uuid.UUID) -> MagicMock:
    routine = MagicMock()
    routine.id = routine_id
    routine.name = "Opening"
    routine.category = RoutineCategory.opening
    return routine


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.account_id = uuid.uuid4()
    return ctx


class TestListExecutionsStatusFilter:
    """Verify status_filter works correctly with pending→missed remapping."""

    async def _call_list_executions(
        self,
        executions: list[MagicMock],
        status_filter: ExecutionStatus | None,
        mock_session: AsyncMock,
        mock_context: MagicMock,
    ):
        """Helper to call list_executions with mocked repos."""
        # Build routine lookup from executions
        routine_ids = {e.routine_id for e in executions}
        routines = [_make_routine(rid) for rid in routine_ids]

        with (
            patch(f"{_BASE}.RoutineExecutionRepositoryAsync") as mock_exec_repo_cls,
            patch(f"{_BASE}.RoutineRepositoryAsync") as mock_routine_repo_cls,
            patch(f"{_BASE}.RoutineSubmissionRepositoryAsync") as mock_sub_repo_cls,
        ):
            mock_exec_repo = mock_exec_repo_cls.return_value
            mock_exec_repo.list_executions_by_project = AsyncMock(
                return_value=executions
            )

            mock_routine_repo = mock_routine_repo_cls.return_value
            mock_routine_repo.list_routines_by_project = AsyncMock(
                return_value=routines
            )
            mock_routine_repo.list_items_by_routine_ids = AsyncMock(return_value={})

            mock_sub_repo = mock_sub_repo_cls.return_value
            mock_sub_repo.list_submissions_by_execution_ids = AsyncMock(return_value=[])
            mock_sub_repo.list_responses_by_submission_ids = AsyncMock(return_value={})

            result = await list_executions(
                project_id=uuid.uuid4(),
                context=mock_context,
                session=mock_session,
                status_filter=status_filter,
            )

            return result, mock_exec_repo

    @pytest.mark.asyncio
    async def test_filter_pending_excludes_missed(
        self, mock_session, mock_context
    ) -> None:
        """status_filter=pending should not return past-deadline executions."""
        now = datetime.now(timezone.utc)
        still_pending = _make_execution(scheduled_end=now + timedelta(hours=1))
        past_deadline = _make_execution(scheduled_end=now - timedelta(hours=1))

        result, _ = await self._call_list_executions(
            [still_pending, past_deadline],
            ExecutionStatus.pending,
            mock_session,
            mock_context,
        )

        statuses = [e.status for e in result.executions]
        assert statuses == [ExecutionStatus.pending]
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_filter_missed_returns_past_deadline(
        self, mock_session, mock_context
    ) -> None:
        """status_filter=missed should return past-deadline pending executions."""
        now = datetime.now(timezone.utc)
        still_pending = _make_execution(scheduled_end=now + timedelta(hours=1))
        past_deadline = _make_execution(scheduled_end=now - timedelta(hours=1))

        result, _ = await self._call_list_executions(
            [still_pending, past_deadline],
            ExecutionStatus.missed,
            mock_session,
            mock_context,
        )

        # Should only include the past-deadline one, remapped to missed
        statuses = [e.status for e in result.executions]
        assert statuses == [ExecutionStatus.missed]
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_filter_missed_queries_db_for_pending(
        self, mock_session, mock_context
    ) -> None:
        """status_filter=missed should query the DB with status=pending."""
        _, mock_repo = await self._call_list_executions(
            [], ExecutionStatus.missed, mock_session, mock_context
        )

        call_kwargs = mock_repo.list_executions_by_project.call_args[1]
        assert call_kwargs["status"] == ExecutionStatus.pending

    @pytest.mark.asyncio
    async def test_no_filter_returns_all_with_remap(
        self, mock_session, mock_context
    ) -> None:
        """No status_filter should return all executions with correct statuses."""
        now = datetime.now(timezone.utc)
        still_pending = _make_execution(scheduled_end=now + timedelta(hours=1))
        past_deadline = _make_execution(scheduled_end=now - timedelta(hours=1))

        result, _ = await self._call_list_executions(
            [still_pending, past_deadline], None, mock_session, mock_context
        )

        statuses = {e.status for e in result.executions}
        assert statuses == {ExecutionStatus.pending, ExecutionStatus.missed}
        assert result.total == 2
