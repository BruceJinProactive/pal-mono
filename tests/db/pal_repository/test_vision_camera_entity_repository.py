"""Tests for db.pal_repository.VisionCameraEntityRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_camera_entity import VisionCameraEntityData
from db.pal_repository.vision_camera_entity import VisionCameraEntityRepository
from db.tables.vision_camera_entities import VisionCameraEntity


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionCameraEntityRepository:
    return VisionCameraEntityRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_camera_config_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_entity_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_camera_config_id: uuid.UUID,
    sample_entity_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=VisionCameraEntity)
    row.id = sample_id
    row.camera_config_id = sample_camera_config_id
    row.entity_id = sample_entity_id
    row.roi_hint = {"x": 10, "y": 20}
    row.created_at = datetime(2026, 4, 29, tzinfo=timezone.utc)
    return row


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_returns_none(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_camera_config_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        input_data = VisionCameraEntityData(
            id=sample_id,
            camera_config_id=sample_camera_config_id,
            entity_id=sample_entity_id,
            roi_hint={"x": 10, "y": 20},
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
        sample_camera_config_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = VisionCameraEntityData(
            id=sample_id,
            camera_config_id=sample_camera_config_id,
            entity_id=sample_entity_id,
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )

        with pytest.raises(Exception):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VisionCameraEntityData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestGetByCameraAndEntity:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_camera_config_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_camera_and_entity(
            sample_camera_config_id, sample_entity_id
        )

        assert isinstance(data, VisionCameraEntityData)
        assert data.camera_config_id == sample_camera_config_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_camera_and_entity(uuid.uuid4(), uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        data = await repo.get_by_camera_and_entity(uuid.uuid4(), uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestListByCamera:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_camera_config_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_camera(sample_camera_config_id)

        assert len(results) == 1
        assert isinstance(results[0], VisionCameraEntityData)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_camera(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_camera(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()


class TestListByEntity:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_entity_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_entity(sample_entity_id)

        assert len(results) == 1
        assert isinstance(results[0], VisionCameraEntityData)

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_entity(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, roi_hint={"x": 50})

        assert isinstance(data, VisionCameraEntityData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), roi_hint={"x": 50})
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionCameraEntityRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("update failed")

        with pytest.raises(Exception):
            await repo.update(sample_id, roi_hint={"x": 50})
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionCameraEntityRepository,
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
        self, repo: VisionCameraEntityRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.delete(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionCameraEntityRepository,
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
        data = VisionCameraEntityData(
            id=uuid.uuid4(),
            camera_config_id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            roi_hint={"x": 10},
            created_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.roi_hint = {"changed": True}  # type: ignore[misc]
