"""Tests for db.pal_repository.MonitoringConfigRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only MonitoringConfigData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.monitoring_config import MonitoringConfigData
from db.pal_repository.monitoring_config import MonitoringConfigRepository, _to_data
from db.tables.monitoring_configs import MonitoringConfig


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> MonitoringConfigRepository:
    return MonitoringConfigRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=MonitoringConfig)
    row.id = sample_id
    row.project_id = uuid.uuid4()
    row.signal_source_id = uuid.uuid4()
    row.name = "Test Config"
    row.enabled = True
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.description = "A test config"
    row.rules = {"threshold": 0.8, "reference_images": [{"url": "s3://img"}]}
    row.tags = ["alert", "critical"]
    row.updated_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, MonitoringConfigData)
        assert data.id == sample_orm_row.id
        assert data.project_id == sample_orm_row.project_id
        assert data.name == "Test Config"
        assert data.enabled is True
        assert data.description == "A test config"
        assert data.tags == ("alert", "critical")
        assert data.rules["threshold"] == 0.8
        assert data.updated_at == sample_orm_row.updated_at

    def test_converts_none_rules_and_tags(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.rules = None
        sample_orm_row.tags = None
        data = _to_data(sample_orm_row)
        assert dict(data.rules) == {}
        assert data.tags == ()


# ---------------------------------------------------------------------------
# MonitoringConfigData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: MonitoringConfigRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = MonitoringConfigData(
            id=sample_id,
            project_id=uuid.uuid4(),
            signal_source_id=uuid.uuid4(),
            name="Test",
            enabled=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]

    def test_rules_is_mapping_proxy(self, sample_id: uuid.UUID) -> None:
        data = MonitoringConfigData(
            id=sample_id,
            project_id=uuid.uuid4(),
            signal_source_id=uuid.uuid4(),
            name="Test",
            enabled=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            rules={"key": "value"},
        )
        assert isinstance(data.rules, MappingProxyType)
        with pytest.raises(TypeError):
            data.rules["key"] = "new"  # type: ignore[index]

    def test_tags_is_tuple(self, sample_id: uuid.UUID) -> None:
        data = MonitoringConfigData(
            id=sample_id,
            project_id=uuid.uuid4(),
            signal_source_id=uuid.uuid4(),
            name="Test",
            enabled=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tags=("a", "b"),
        )
        assert isinstance(data.tags, tuple)

    def test_rules_deepcopy_prevents_nested_mutation(
        self, sample_id: uuid.UUID
    ) -> None:
        original = {"nested": [1, 2, 3]}
        data = MonitoringConfigData(
            id=sample_id,
            project_id=uuid.uuid4(),
            signal_source_id=uuid.uuid4(),
            name="Test",
            enabled=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            rules=original,
        )
        # Mutating the original dict should not affect the data object
        original["nested"].append(4)
        assert list(data.rules["nested"]) == [1, 2, 3]


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: MonitoringConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)
        assert isinstance(data, MonitoringConfigData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: MonitoringConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: MonitoringConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_project_id
# ---------------------------------------------------------------------------


class TestGetByProjectId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: MonitoringConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_project_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], MonitoringConfigData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: MonitoringConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_project_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: MonitoringConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_project_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()
