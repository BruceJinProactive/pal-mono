"""Tests for db.pal_repository.VisionEntityTypeRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only VisionEntityTypeData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_entity_type import VisionEntityTypeData
from db.pal_repository.vision_entity_type import VisionEntityTypeRepository
from db.tables.vision_entity_types import VisionEntityType


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionEntityTypeRepository:
    return VisionEntityTypeRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_account_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=VisionEntityType)
    row.id = sample_id
    row.account_id = sample_account_id
    row.name = "table"
    row.display_name = "Table"
    row.description = "Dining tables"
    row.icon = None
    row.is_active = True
    row.created_at = datetime(2026, 4, 29, tzinfo=timezone.utc)
    row.updated_at = None
    return row


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_returns_none(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_account_id: uuid.UUID,
    ) -> None:
        input_data = VisionEntityTypeData(
            id=sample_id,
            account_id=sample_account_id,
            name="table",
            display_name="Table",
            description="Dining tables",
            is_active=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = VisionEntityTypeData(
            id=sample_id,
            account_id=sample_account_id,
            name="table",
            display_name="Table",
            is_active=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        with pytest.raises(Exception):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VisionEntityTypeData)
        assert data.id == sample_id
        assert data.name == "table"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestGetByAccount:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_account(sample_account_id)

        assert len(results) == 1
        assert isinstance(results[0], VisionEntityTypeData)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_account(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.get_by_account(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()


class TestGetByAccountAndName:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_account_and_name(sample_account_id, "table")

        assert isinstance(data, VisionEntityTypeData)
        assert data.name == "table"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_account_and_name(uuid.uuid4(), "missing")
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        data = await repo.get_by_account_and_name(uuid.uuid4(), "table")
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, display_name="Dining Table")

        assert isinstance(data, VisionEntityTypeData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), display_name="X")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("update failed")

        with pytest.raises(Exception):
            await repo.update(sample_id, display_name="X")
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        result = await repo.delete(sample_id)

        assert result is True
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self, repo: VisionEntityTypeRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.delete(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityTypeRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete(sample_id)
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_data_is_frozen(self) -> None:
        data = VisionEntityTypeData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            name="table",
            display_name="Table",
            is_active=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]
