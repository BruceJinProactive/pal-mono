"""Tests for new RoutineExecutionRepositoryAsync methods."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.routine_execution_repository import RoutineExecutionRepositoryAsync


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def repo(mock_session):
    return RoutineExecutionRepositoryAsync(mock_session)


# ---------------------------------------------------------------------------
# update_execution — scheduled_start / scheduled_end
# ---------------------------------------------------------------------------


class TestUpdateExecutionTimeFields:
    """Cover the scheduled_start/scheduled_end branches (lines 317-320)."""

    @pytest.mark.asyncio
    async def test_updates_scheduled_start_and_end(self, repo, mock_session) -> None:
        execution = MagicMock()
        new_start = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 3, 1, 22, 0, tzinfo=timezone.utc)

        with patch.object(repo, "get_execution_by_id", return_value=execution):
            result = await repo.update_execution(
                execution_id=uuid.uuid4(),
                scheduled_start=new_start,
                scheduled_end=new_end,
            )

        assert execution.scheduled_start == new_start
        assert execution.scheduled_end == new_end
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(execution)
        assert result is execution

    @pytest.mark.asyncio
    async def test_no_update_when_none(self, repo) -> None:
        execution = MagicMock()
        original_start = execution.scheduled_start
        original_end = execution.scheduled_end

        with patch.object(repo, "get_execution_by_id", return_value=execution):
            await repo.update_execution(execution_id=uuid.uuid4())

        assert execution.scheduled_start == original_start
        assert execution.scheduled_end == original_end

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, repo) -> None:
        with patch.object(repo, "get_execution_by_id", return_value=None):
            result = await repo.update_execution(
                execution_id=uuid.uuid4(),
                scheduled_start=datetime.now(timezone.utc),
            )
        assert result is None


# ---------------------------------------------------------------------------
# find_todays_pending_executions
# ---------------------------------------------------------------------------


class TestFindTodaysPendingExecutions:
    """Cover lines 347-361."""

    @pytest.mark.asyncio
    async def test_returns_results(self, repo, mock_session) -> None:
        fake_exec = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fake_exec]
        mock_session.execute.return_value = mock_result

        result = await repo.find_todays_pending_executions(
            schedule_id=uuid.uuid4(),
            today_start_utc=datetime(2026, 2, 27, 8, 0, tzinfo=timezone.utc),
            today_end_utc=datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc),
        )

        assert result == [fake_exec]
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, repo, mock_session) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        result = await repo.find_todays_pending_executions(
            schedule_id=uuid.uuid4(),
            today_start_utc=datetime(2026, 2, 27, 8, 0, tzinfo=timezone.utc),
            today_end_utc=datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc),
        )

        assert result == []
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# find_pending_executions_from
# ---------------------------------------------------------------------------


class TestFindPendingExecutionsFrom:
    """Cover lines 518-531."""

    @pytest.mark.asyncio
    async def test_returns_results(self, repo, mock_session) -> None:
        fake_exec = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fake_exec]
        mock_session.execute.return_value = mock_result

        result = await repo.find_pending_executions_from(
            schedule_id=uuid.uuid4(),
            from_utc=datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc),
        )

        assert result == [fake_exec]
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, repo, mock_session) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        result = await repo.find_pending_executions_from(
            schedule_id=uuid.uuid4(),
            from_utc=datetime(2026, 2, 28, 8, 0, tzinfo=timezone.utc),
        )

        assert result == []
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_executions_by_project — sort order
# ---------------------------------------------------------------------------


class TestListExecutionsByProjectSortOrder:
    """Verify list_executions_by_project sorts by scheduled_start ascending."""

    @pytest.mark.asyncio
    async def test_sorts_ascending_by_scheduled_start(self, repo, mock_session) -> None:
        fake_exec = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fake_exec]
        mock_session.execute.return_value = mock_result

        result = await repo.list_executions_by_project(
            project_id=uuid.uuid4(),
        )

        assert result == [fake_exec]
        # Verify the SQL statement was built with .asc() by inspecting the
        # compiled statement passed to session.execute
        executed_stmt = mock_session.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "asc" in compiled.lower()
