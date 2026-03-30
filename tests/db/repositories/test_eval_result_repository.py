"""Tests for EvalResultRepositoryAsync."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.eval_result_repository import EvalResultRepositoryAsync
from db.tables import EvalResult


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> EvalResultRepositoryAsync:
    return EvalResultRepositoryAsync(mock_session)


def make_eval_result(**kwargs: object) -> MagicMock:
    """Return a MagicMock that looks like an EvalResult."""
    result = MagicMock(spec=EvalResult)
    result.id = kwargs.get("id", uuid.uuid4())
    result.eval_run_id = kwargs.get("eval_run_id", uuid.uuid4())
    result.scenario_id = kwargs.get("scenario_id", "scenario-001")
    result.metric_name = kwargs.get("metric_name", "accuracy")
    result.score = kwargs.get("score", 1.0)
    result.passed = kwargs.get("passed", True)
    result.reason = kwargs.get("reason", None)
    result.raw_output = kwargs.get("raw_output", None)
    result.conversation_id = kwargs.get("conversation_id", None)
    result.agent_fingerprint = kwargs.get("agent_fingerprint", None)
    return result


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        eval_result = make_eval_result()

        returned = await repo.create(eval_result)

        mock_session.add.assert_called_once_with(eval_result)
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(eval_result)
        assert returned is eval_result

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_propagates_and_rolls_back(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.flush.side_effect = SQLAlchemyError("db error")
        eval_result = make_eval_result()

        with pytest.raises(SQLAlchemyError):
            await repo.create(eval_result)

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_batch
# ---------------------------------------------------------------------------


class TestCreateBatch:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_without_touching_session(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        returned = await repo.create_batch([])

        assert returned == []
        mock_session.add_all.assert_not_called()
        mock_session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_nonempty_list_calls_add_all_and_refreshes_each(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        results = [make_eval_result(), make_eval_result()]

        returned = await repo.create_batch(results)

        mock_session.add_all.assert_called_once_with(results)
        mock_session.flush.assert_awaited_once()
        assert mock_session.refresh.await_count == 2
        mock_session.refresh.assert_has_awaits([call(r) for r in results])
        assert returned == list(results)

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_rolls_back_and_raises(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.flush.side_effect = SQLAlchemyError("batch error")
        results = [make_eval_result()]

        with pytest.raises(SQLAlchemyError):
            await repo.create_batch(results)

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_run_id
# ---------------------------------------------------------------------------


class TestGetByRunId:
    @pytest.mark.asyncio
    async def test_returns_all_results_for_run(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        eval_run_id = uuid.uuid4()
        fake_result = make_eval_result(eval_run_id=eval_run_id)
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [fake_result]
        mock_session.execute.return_value = mock_execute_result

        returned = await repo.get_by_run_id(eval_run_id)

        assert returned == [fake_result]
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_found(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        returned = await repo.get_by_run_id(uuid.uuid4())

        assert returned == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_sqlalchemy_error(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        returned = await repo.get_by_run_id(uuid.uuid4())

        assert returned == []
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_scenario
# ---------------------------------------------------------------------------


class TestGetByScenario:
    @pytest.mark.asyncio
    async def test_filters_by_run_id_and_scenario_id(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        eval_run_id = uuid.uuid4()
        scenario_id = "scenario-42"
        fake_result = make_eval_result(eval_run_id=eval_run_id, scenario_id=scenario_id)
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [fake_result]
        mock_session.execute.return_value = mock_execute_result

        returned = await repo.get_by_scenario(eval_run_id, scenario_id)

        assert returned == [fake_result]
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        returned = await repo.get_by_scenario(uuid.uuid4(), "no-such-scenario")

        assert returned == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_sqlalchemy_error(
        self, repo: EvalResultRepositoryAsync, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        returned = await repo.get_by_scenario(uuid.uuid4(), "scenario-x")

        assert returned == []
        mock_session.rollback.assert_awaited_once()
