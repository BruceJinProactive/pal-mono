"""Tests for db.pal_repository.MonitoringRunRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only MonitoringRunData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.monitoring_run import MonitoringRunData
from db.pal_repository.monitoring_run import MonitoringRunRepository, _to_data
from db.tables.monitoring_runs import MonitoringRun


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> MonitoringRunRepository:
    return MonitoringRunRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=MonitoringRun)
    row.id = sample_id
    row.monitoring_config_id = uuid.uuid4()
    row.started_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.trigger_metadata = {"source": "cron"}
    row.evaluation_result = {"score": 0.95}
    row.completed_at = datetime(2025, 6, 1, 0, 5, tzinfo=timezone.utc)
    row.result = "pass"
    row.details = "All checks passed"
    row.confidence = 95
    row.error_message = None
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, MonitoringRunData)
        assert data.id == sample_orm_row.id
        assert data.monitoring_config_id == sample_orm_row.monitoring_config_id
        assert data.trigger_metadata["source"] == "cron"
        assert data.evaluation_result["score"] == 0.95
        assert data.result == "pass"
        assert data.details == "All checks passed"
        assert data.confidence == 95
        assert data.error_message is None

    def test_converts_none_metadata_and_result(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.trigger_metadata = None
        sample_orm_row.evaluation_result = None
        data = _to_data(sample_orm_row)
        assert dict(data.trigger_metadata) == {}
        assert dict(data.evaluation_result) == {}


# ---------------------------------------------------------------------------
# MonitoringRunData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: MonitoringRunRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = MonitoringRunData(
            id=sample_id,
            monitoring_config_id=uuid.uuid4(),
            started_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.result = "fail"  # type: ignore[misc]

    def test_trigger_metadata_is_mapping_proxy(self, sample_id: uuid.UUID) -> None:
        data = MonitoringRunData(
            id=sample_id,
            monitoring_config_id=uuid.uuid4(),
            started_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            trigger_metadata={"key": "value"},
        )
        assert isinstance(data.trigger_metadata, MappingProxyType)
        with pytest.raises(TypeError):
            data.trigger_metadata["key"] = "new"  # type: ignore[index]

    def test_evaluation_result_is_mapping_proxy(self, sample_id: uuid.UUID) -> None:
        data = MonitoringRunData(
            id=sample_id,
            monitoring_config_id=uuid.uuid4(),
            started_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            evaluation_result={"score": 1.0},
        )
        assert isinstance(data.evaluation_result, MappingProxyType)


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: MonitoringRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)
        assert isinstance(data, MonitoringRunData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: MonitoringRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: MonitoringRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_config_id
# ---------------------------------------------------------------------------


class TestGetByConfigId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: MonitoringRunRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_config_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], MonitoringRunData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: MonitoringRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_config_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: MonitoringRunRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_config_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()
