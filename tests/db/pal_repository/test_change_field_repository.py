"""Tests for db.pal_repository.ChangeFieldRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ChangeFieldData instances are returned.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.change_field import ChangeFieldRepository, _to_data
from db.pal_repository.data_classes.change_field import ChangeFieldData
from db.tables.change_log import ChangeField


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ChangeFieldRepository:
    return ChangeFieldRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=ChangeField)
    row.id = sample_id
    row.change_log_id = uuid.uuid4()
    row.field = "name"
    row.old_value = "Old Name"
    row.new_value = "New Name"
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, ChangeFieldData)
        assert data.id == sample_orm_row.id
        assert data.change_log_id == sample_orm_row.change_log_id
        assert data.field == "name"
        assert data.old_value == "Old Name"
        assert data.new_value == "New Name"

    def test_converts_none_values(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.old_value = None
        sample_orm_row.new_value = None
        data = _to_data(sample_orm_row)
        assert data.old_value is None
        assert data.new_value is None


# ---------------------------------------------------------------------------
# ChangeFieldData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: ChangeFieldRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = ChangeFieldData(
            id=sample_id,
            change_log_id=uuid.uuid4(),
            field="name",
            old_value="old",
            new_value="new",
        )
        with pytest.raises(AttributeError):
            data.field = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_by_change_log_id
# ---------------------------------------------------------------------------


class TestGetByChangeLogId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: ChangeFieldRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        change_log_id = sample_orm_row.change_log_id
        results = await repo.get_by_change_log_id(change_log_id)
        mock_session.execute.assert_awaited_once()
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], ChangeFieldData)
        assert results[0].change_log_id == change_log_id
        assert results[0].field == sample_orm_row.field

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: ChangeFieldRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_change_log_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: ChangeFieldRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_change_log_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()
