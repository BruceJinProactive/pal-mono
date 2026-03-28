"""Tests for EvalRunRepositoryAsync."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.eval_run_repository import EvalRunRepositoryAsync
from db.tables import EvalRun


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> EvalRunRepositoryAsync:
    return EvalRunRepositoryAsync(mock_session)


def make_eval_run(**kwargs: object) -> MagicMock:
    """Return a MagicMock that looks like an EvalRun."""
    run = MagicMock(spec=EvalRun)
    run.id = kwargs.get("id", uuid.uuid4())
    run.project_id = kwargs.get("project_id", uuid.uuid4())
    run.account_id = kwargs.get("account_id", uuid.uuid4())
    run.agent_fingerprint = kwargs.get("agent_fingerprint", None)
    run.driver_mode = kwargs.get("driver_mode", "sync")
    run.status = kwargs.get("status", "pending")
    run.triggered_by = kwargs.get("triggered_by", "api")
    run.scenario_count = kwargs.get("scenario_count", 0)
    run.passed_count = kwargs.get("passed_count", 0)
    run.failed_count = kwargs.get("failed_count", 0)
    run.overall_score = kwargs.get("overall_score", None)
    run.started_at = kwargs.get("started_at", None)
    run.completed_at = kwargs.get("completed_at", None)
    run.error_message = kwargs.get("error_message", None)
    run.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
    run.updated_at = kwargs.get("updated_at", None)
    return run


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_happy_path_returns_run(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run()

        result = await repo.create(run)

        mock_session.add.assert_called_once_with(run)
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(run)
        assert result is run

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_rolls_back_and_raises(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.flush.side_effect = SQLAlchemyError("db error")
        run = make_eval_run()

        with pytest.raises(SQLAlchemyError):
            await repo.create(run)

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found_returns_run(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(run.id)

        assert result is run
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_returns_none(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_rolls_back_and_raises(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_project
# ---------------------------------------------------------------------------


class TestGetByProject:
    @pytest.mark.asyncio
    async def test_no_filters_returns_all_runs(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run1 = make_eval_run()
        run2 = make_eval_run()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [run1, run2]
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_project(uuid.uuid4())

        assert result == [run1, run2]
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status_filter_applied(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run(status="completed")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [run]
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_project(uuid.uuid4(), status="completed")

        assert result == [run]
        # Verify the compiled query mentions the status filter
        executed_stmt = mock_session.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "completed" in compiled

    @pytest.mark.asyncio
    async def test_date_filters_applied(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 3, 1, tzinfo=timezone.utc)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repo.get_by_project(uuid.uuid4(), start_date=start, end_date=end)

        executed_stmt = mock_session.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "started_at" in compiled

    @pytest.mark.asyncio
    async def test_orders_by_created_at_desc(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await repo.get_by_project(uuid.uuid4())

        executed_stmt = mock_session.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "desc" in compiled.lower()

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_rolls_back_and_raises(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_project(uuid.uuid4())

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_updates_status_and_timestamps(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run()
        now = datetime.now(timezone.utc)

        with patch.object(repo, "get_by_id", return_value=run):
            result = await repo.update_status(
                run.id,
                "running",
                started_at=now,
            )

        assert run.status == "running"
        assert run.started_at == now
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(run)
        assert result is run

    @pytest.mark.asyncio
    async def test_run_not_found_returns_none(
        self, repo: EvalRunRepositoryAsync
    ) -> None:
        with patch.object(repo, "get_by_id", return_value=None):
            result = await repo.update_status(uuid.uuid4(), "completed")

        assert result is None

    @pytest.mark.asyncio
    async def test_partial_kwargs_leaves_other_fields_unchanged(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run(completed_at=None, error_message=None)
        now = datetime.now(timezone.utc)

        with patch.object(repo, "get_by_id", return_value=run):
            await repo.update_status(run.id, "running", started_at=now)

        assert run.started_at == now
        assert run.completed_at is None
        assert run.error_message is None

    @pytest.mark.asyncio
    async def test_sets_error_message_and_completed_at(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run()
        completed = datetime.now(timezone.utc)

        with patch.object(repo, "get_by_id", return_value=run):
            await repo.update_status(
                run.id,
                "failed",
                completed_at=completed,
                error_message="timeout",
            )

        assert run.status == "failed"
        assert run.completed_at == completed
        assert run.error_message == "timeout"


# ---------------------------------------------------------------------------
# update_counts
# ---------------------------------------------------------------------------


class TestUpdateCounts:
    @pytest.mark.asyncio
    async def test_updates_counts_and_score(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run()

        with patch.object(repo, "get_by_id", return_value=run):
            result = await repo.update_counts(
                run.id,
                scenario_count=10,
                passed_count=8,
                failed_count=2,
                overall_score=0.8,
            )

        assert run.scenario_count == 10
        assert run.passed_count == 8
        assert run.failed_count == 2
        assert run.overall_score == 0.8
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(run)
        assert result is run

    @pytest.mark.asyncio
    async def test_run_not_found_returns_none(
        self, repo: EvalRunRepositoryAsync
    ) -> None:
        with patch.object(repo, "get_by_id", return_value=None):
            result = await repo.update_counts(uuid.uuid4(), scenario_count=5)

        assert result is None

    @pytest.mark.asyncio
    async def test_none_kwargs_leave_fields_unchanged(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run(
            scenario_count=3, passed_count=2, failed_count=1, overall_score=0.5
        )
        original_scenario = run.scenario_count
        original_passed = run.passed_count

        with patch.object(repo, "get_by_id", return_value=run):
            await repo.update_counts(run.id)  # no kwargs — nothing should change

        assert run.scenario_count == original_scenario
        assert run.passed_count == original_passed

    @pytest.mark.asyncio
    async def test_partial_update_only_changes_provided_fields(
        self, repo: EvalRunRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        run = make_eval_run(passed_count=0, failed_count=0, overall_score=None)

        with patch.object(repo, "get_by_id", return_value=run):
            await repo.update_counts(run.id, passed_count=5)

        assert run.passed_count == 5
        assert run.failed_count == 0
        assert run.overall_score is None
