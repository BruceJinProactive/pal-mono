"""Tests for db.pal_repository.ChangeLogRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ChangeLogData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.change_log import ChangeLogRepository, _field_to_data, _to_data
from db.pal_repository.data_classes.change_field import ChangeFieldData
from db.pal_repository.data_classes.change_log import ChangeLogData
from db.tables.change_log import ChangeField, ChangeLog


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ChangeLogRepository:
    return ChangeLogRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_field_row() -> MagicMock:
    row = MagicMock(spec=ChangeField)
    row.id = uuid.uuid4()
    row.change_log_id = uuid.uuid4()
    row.field = "name"
    row.old_value = "Old Name"
    row.new_value = "New Name"
    return row


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID, sample_field_row: MagicMock) -> MagicMock:
    row = MagicMock(spec=ChangeLog)
    row.id = sample_id
    row.account_id = uuid.uuid4()
    row.resource_type = MagicMock(value="Account")
    row.resource_id = "res-123"
    row.author = "admin@test.com"
    row.action = MagicMock(value="Update")
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.fields = [sample_field_row]
    return row


# ---------------------------------------------------------------------------
# _field_to_data / _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_field_to_data(self, sample_field_row: MagicMock) -> None:
        data = _field_to_data(sample_field_row)
        assert isinstance(data, ChangeFieldData)
        assert data.id == sample_field_row.id
        assert data.change_log_id == sample_field_row.change_log_id
        assert data.field == "name"
        assert data.old_value == "Old Name"
        assert data.new_value == "New Name"

    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, ChangeLogData)
        assert data.id == sample_orm_row.id
        assert data.account_id == sample_orm_row.account_id
        assert data.resource_type == "Account"
        assert data.resource_id == "res-123"
        assert data.author == "admin@test.com"
        assert data.action == "Update"
        assert isinstance(data.fields, tuple)
        assert len(data.fields) == 1
        assert isinstance(data.fields[0], ChangeFieldData)

    def test_converts_empty_fields(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.fields = []
        data = _to_data(sample_orm_row)
        assert data.fields == ()

    def test_converts_none_fields(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.fields = None
        data = _to_data(sample_orm_row)
        assert data.fields == ()


# ---------------------------------------------------------------------------
# ChangeLogData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: ChangeLogRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = ChangeLogData(
            id=sample_id,
            account_id=uuid.uuid4(),
            resource_type="Account",
            resource_id="res-123",
            author="admin@test.com",
            action="Update",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.action = "Delete"  # type: ignore[misc]

    def test_fields_is_tuple(self, sample_id: uuid.UUID) -> None:
        field_data = ChangeFieldData(
            id=uuid.uuid4(),
            change_log_id=sample_id,
            field="name",
            old_value="old",
            new_value="new",
        )
        data = ChangeLogData(
            id=sample_id,
            account_id=uuid.uuid4(),
            resource_type="Account",
            resource_id="res-123",
            author="admin@test.com",
            action="Update",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            fields=(field_data,),
        )
        assert isinstance(data.fields, tuple)


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: ChangeLogRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)
        assert isinstance(data, ChangeLogData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: ChangeLogRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: ChangeLogRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_resource
# ---------------------------------------------------------------------------


class TestGetByResource:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: ChangeLogRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_resource("Account", "res-123")
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], ChangeLogData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: ChangeLogRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_resource("Account", "res-999")
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: ChangeLogRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_resource("Account", "res-123")
        mock_session.rollback.assert_awaited_once()
