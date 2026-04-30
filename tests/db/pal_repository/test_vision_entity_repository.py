"""Tests for db.pal_repository.VisionEntityRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.pal_repository.vision_entity import VisionEntityRepository
from db.tables.vision_entities import VisionEntity


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionEntityRepository:
    return VisionEntityRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_entity_type_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_project_id: uuid.UUID,
    sample_entity_type_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=VisionEntity)
    row.id = sample_id
    row.project_id = sample_project_id
    row.entity_type_id = sample_entity_type_id
    row.name = "Table 1"
    row.current_state_id = None
    row.current_state_since = None
    row.entity_metadata = {"seats": 4}
    row.is_active = True
    row.created_at = datetime(2026, 4, 29, tzinfo=timezone.utc)
    row.updated_at = None
    return row


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_returns_none(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_project_id: uuid.UUID,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        input_data = VisionEntityData(
            id=sample_id,
            project_id=sample_project_id,
            entity_type_id=sample_entity_type_id,
            name="Table 1",
            entity_metadata={"seats": 4},
            is_active=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_project_id: uuid.UUID,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = VisionEntityData(
            id=sample_id,
            project_id=sample_project_id,
            entity_type_id=sample_entity_type_id,
            name="Table 1",
            entity_metadata={},
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
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VisionEntityData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestListByProject:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project(sample_project_id)

        assert len(results) == 1
        assert isinstance(results[0], VisionEntityData)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_project(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_filters_by_entity_type(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project(
            sample_project_id, entity_type_id=sample_entity_type_id
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filters_by_current_state(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        state_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project(
            sample_project_id, current_state_id=state_id
        )

        assert len(results) == 1


class TestGetByProjectTypeAndName:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_type_and_name(
            sample_project_id, sample_entity_type_id, "Table 1"
        )

        assert isinstance(data, VisionEntityData)
        assert data.name == "Table 1"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_type_and_name(
            uuid.uuid4(), uuid.uuid4(), "missing"
        )
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        data = await repo.get_by_project_type_and_name(
            uuid.uuid4(), uuid.uuid4(), "Table 1"
        )
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, name="Table 2")

        assert isinstance(data, VisionEntityData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), name="X")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("update failed")

        with pytest.raises(Exception):
            await repo.update(sample_id, name="X")
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionEntityRepository,
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
        self, repo: VisionEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.delete(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityRepository,
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
        data = VisionEntityData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            entity_type_id=uuid.uuid4(),
            name="Table 1",
            entity_metadata={},
            is_active=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]
