"""Tests for db.pal_repository.EvalRunRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only EvalRunData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.eval_run import EvalRunData
from db.pal_repository.eval_run import EvalRunRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> EvalRunRepository:
    return EvalRunRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.project_id = uuid.uuid4()
    row.account_id = uuid.uuid4()
    row.driver_mode = "automatic"
    row.status = "completed"
    row.triggered_by = "system"
    row.scenario_count = 10
    row.passed_count = 8
    row.failed_count = 2
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.agent_fingerprint = None
    row.overall_score = None
    row.started_at = None
    row.completed_at = None
    row.error_message = None
    row.updated_at = None
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(sample_id)
        assert isinstance(data, EvalRunData)
        assert data.id == sample_id
        assert data.status == "completed"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: EvalRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: EvalRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())


class TestGetByProject:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_project(uuid.uuid4())
        assert len(results) == 1
        assert results[0].driver_mode == "automatic"

    @pytest.mark.asyncio
    async def test_with_all_filters(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_project(
            uuid.uuid4(),
            status="completed",
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: EvalRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_project(uuid.uuid4())


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(return_value=None)

        def populate_on_refresh(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.project_id = sample_orm_row.project_id
            row.account_id = sample_orm_row.account_id
            row.driver_mode = sample_orm_row.driver_mode
            row.status = sample_orm_row.status
            row.triggered_by = sample_orm_row.triggered_by
            row.scenario_count = sample_orm_row.scenario_count
            row.passed_count = sample_orm_row.passed_count
            row.failed_count = sample_orm_row.failed_count
            row.created_at = sample_orm_row.created_at
            row.agent_fingerprint = sample_orm_row.agent_fingerprint
            row.overall_score = sample_orm_row.overall_score
            row.started_at = sample_orm_row.started_at
            row.completed_at = sample_orm_row.completed_at
            row.error_message = sample_orm_row.error_message
            row.updated_at = sample_orm_row.updated_at

        mock_session.refresh = AsyncMock(side_effect=populate_on_refresh)

        record = EvalRunData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            driver_mode="automatic",
            status="pending",
            triggered_by="api",
            scenario_count=0,
            passed_count=0,
            failed_count=0,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        data = await repo.create(record)
        assert isinstance(data, EvalRunData)
        assert data.status == "completed"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: EvalRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        record = EvalRunData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            driver_mode="automatic",
            status="pending",
            triggered_by="api",
            scenario_count=0,
            passed_count=0,
            failed_count=0,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(record)
        mock_session.rollback.assert_awaited_once()


class TestUpdateStatus:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)

        started = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
        completed = datetime(2025, 6, 1, 10, 30, tzinfo=timezone.utc)
        data = await repo.update_status(
            sample_id, "completed", started_at=started, completed_at=completed
        )
        assert data is not None
        assert sample_orm_row.status == "completed"
        assert sample_orm_row.started_at == started
        assert sample_orm_row.completed_at == completed

    @pytest.mark.asyncio
    async def test_updates_with_error_message(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)

        data = await repo.update_status(uuid.uuid4(), "failed", error_message="timeout")
        assert data is not None
        assert sample_orm_row.error_message == "timeout"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: EvalRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.update_status(uuid.uuid4(), "completed")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self,
        repo: EvalRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.update_status(uuid.uuid4(), "failed")
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(
        self, repo: EvalRunRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = EvalRunData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            driver_mode="automatic",
            status="completed",
            triggered_by="system",
            scenario_count=10,
            passed_count=8,
            failed_count=2,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "failed"  # type: ignore[misc]
