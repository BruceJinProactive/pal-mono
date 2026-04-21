"""Tests for db.pal_repository.EvalResultRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.eval_result import EvalResultData
from db.pal_repository.eval_result import EvalResultRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> EvalResultRepository:
    return EvalResultRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.eval_run_id = uuid.uuid4()
    row.scenario_id = "greeting_test"
    row.metric_name = "accuracy"
    row.score = 0.95
    row.passed = True
    row.evaluated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.conversation_id = uuid.uuid4()
    row.agent_fingerprint = None
    row.reason = None
    row.raw_output = {"key": "value"}
    return row


class TestGetByRunId:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: EvalResultRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_run_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].metric_name == "accuracy"

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: EvalResultRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_run_id(uuid.uuid4())


class TestGetByScenario:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: EvalResultRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_scenario(uuid.uuid4(), "greeting_test")
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: EvalResultRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_scenario(uuid.uuid4(), "greeting_test")


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: EvalResultRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(return_value=None)

        def populate_on_refresh(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.eval_run_id = sample_orm_row.eval_run_id
            row.scenario_id = sample_orm_row.scenario_id
            row.metric_name = sample_orm_row.metric_name
            row.score = sample_orm_row.score
            row.passed = sample_orm_row.passed
            row.evaluated_at = sample_orm_row.evaluated_at
            row.conversation_id = sample_orm_row.conversation_id
            row.agent_fingerprint = sample_orm_row.agent_fingerprint
            row.reason = sample_orm_row.reason
            row.raw_output = sample_orm_row.raw_output

        mock_session.refresh = AsyncMock(side_effect=populate_on_refresh)

        record = EvalResultData(
            id=uuid.uuid4(),
            eval_run_id=uuid.uuid4(),
            scenario_id="greeting_test",
            metric_name="accuracy",
            score=0.95,
            passed=True,
            evaluated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        data = await repo.create(record)
        assert data is not None
        assert data.metric_name == "accuracy"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: EvalResultRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        record = EvalResultData(
            id=uuid.uuid4(),
            eval_run_id=uuid.uuid4(),
            scenario_id="greeting_test",
            metric_name="accuracy",
            score=0.95,
            passed=True,
            evaluated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(record)
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(
        self, repo: EvalResultRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = EvalResultData(
            id=uuid.uuid4(),
            eval_run_id=uuid.uuid4(),
            scenario_id="greeting_test",
            metric_name="accuracy",
            score=0.95,
            passed=True,
            evaluated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.score = 0.5  # type: ignore[misc]

    def test_raw_output_is_immutable(self) -> None:
        data = EvalResultData(
            id=uuid.uuid4(),
            eval_run_id=uuid.uuid4(),
            scenario_id="greeting_test",
            metric_name="accuracy",
            score=0.95,
            passed=True,
            evaluated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            raw_output={"key": "value", "nested": {"inner": "val"}},
        )
        with pytest.raises(TypeError):
            data.raw_output["new_key"] = "value"  # type: ignore[index]
        with pytest.raises(TypeError):
            data.raw_output["nested"]["mutate"] = "fail"  # type: ignore[index]

    def test_raw_output_none_is_fine(self) -> None:
        data = EvalResultData(
            id=uuid.uuid4(),
            eval_run_id=uuid.uuid4(),
            scenario_id="greeting_test",
            metric_name="accuracy",
            score=0.95,
            passed=True,
            evaluated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            raw_output=None,
        )
        assert data.raw_output is None
