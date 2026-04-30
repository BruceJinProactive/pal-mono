"""Tests for db.pal_repository.VisionEntityStateDefinitionRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_entity_state_definition import (
    VisionEntityStateDefinitionData,
)
from db.pal_repository.vision_entity_state_definition import (
    VisionEntityStateDefinitionRepository,
)
from db.tables.vision_entity_state_definitions import VisionEntityStateDefinition


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionEntityStateDefinitionRepository:
    return VisionEntityStateDefinitionRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_entity_type_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_entity_type_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=VisionEntityStateDefinition)
    row.id = sample_id
    row.entity_type_id = sample_entity_type_id
    row.name = "clean"
    row.display_name = "Clean"
    row.color = "#00FF00"
    row.sort_order = 0
    row.is_default = True
    row.created_at = datetime(2026, 4, 29, tzinfo=timezone.utc)
    return row


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_returns_none(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        input_data = VisionEntityStateDefinitionData(
            id=sample_id,
            entity_type_id=sample_entity_type_id,
            name="clean",
            display_name="Clean",
            color="#00FF00",
            sort_order=0,
            is_default=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = VisionEntityStateDefinitionData(
            id=sample_id,
            entity_type_id=sample_entity_type_id,
            name="clean",
            display_name="Clean",
            sort_order=0,
            is_default=False,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        with pytest.raises(Exception):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VisionEntityStateDefinitionData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestListByEntityType:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_entity_type(sample_entity_type_id)

        assert len(results) == 1
        assert isinstance(results[0], VisionEntityStateDefinitionData)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_entity_type(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_entity_type(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()


class TestGetByEntityTypeAndName:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_entity_type_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_entity_type_and_name(sample_entity_type_id, "clean")

        assert isinstance(data, VisionEntityStateDefinitionData)
        assert data.name == "clean"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_entity_type_and_name(uuid.uuid4(), "missing")
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        data = await repo.get_by_entity_type_and_name(uuid.uuid4(), "clean")
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, display_name="Dirty")

        assert isinstance(data, VisionEntityStateDefinitionData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), display_name="X")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityStateDefinitionRepository,
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
        repo: VisionEntityStateDefinitionRepository,
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
        self, repo: VisionEntityStateDefinitionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.delete(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityStateDefinitionRepository,
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


class TestCountEntitiesUsingState:

    @pytest.mark.asyncio
    async def test_returns_count(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.all.return_value = [MagicMock(), MagicMock()]
        mock_session.execute.return_value = mock_result

        count = await repo.count_entities_using_state(sample_id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        count = await repo.count_entities_using_state(uuid.uuid4())
        assert count == 0

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionEntityStateDefinitionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.count_entities_using_state(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_data_is_frozen(self) -> None:
        data = VisionEntityStateDefinitionData(
            id=uuid.uuid4(),
            entity_type_id=uuid.uuid4(),
            name="clean",
            display_name="Clean",
            sort_order=0,
            is_default=True,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]
