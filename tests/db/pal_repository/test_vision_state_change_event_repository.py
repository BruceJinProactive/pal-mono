"""Tests for db.pal_repository.VisionStateChangeEventRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from db.pal_repository.vision_state_change_event import VisionStateChangeEventRepository
from db.tables.vision_state_change_events import VisionStateChangeEvent


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionStateChangeEventRepository:
    return VisionStateChangeEventRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_entity_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_new_state_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_entity_id: uuid.UUID,
    sample_new_state_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=VisionStateChangeEvent)
    row.id = sample_id
    row.entity_id = sample_entity_id
    row.new_state_id = sample_new_state_id
    row.observed_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    row.event_metadata = {"source": "camera_1"}
    row.camera_config_id = None
    row.previous_state_id = None
    row.confidence = 0.92
    row.frame_s3_key = None
    return row


@pytest.fixture
def sample_data(
    sample_id: uuid.UUID,
    sample_entity_id: uuid.UUID,
    sample_new_state_id: uuid.UUID,
) -> VisionStateChangeEventData:
    return VisionStateChangeEventData(
        id=sample_id,
        entity_id=sample_entity_id,
        new_state_id=sample_new_state_id,
        observed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        event_metadata={"source": "camera_1"},
        camera_config_id=None,
        previous_state_id=None,
        confidence=0.92,
        frame_s3_key=None,
    )


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_data: VisionStateChangeEventData,
    ) -> None:
        await repo.create(sample_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_data: VisionStateChangeEventData,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        with pytest.raises(Exception):
            await repo.create(sample_data)
        mock_session.rollback.assert_awaited_once()


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VisionStateChangeEventData)
        assert data.id == sample_id
        assert data.confidence == 0.92

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestListByAccount:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        account_id = uuid.uuid4()
        results = await repo.list_by_account(account_id)

        assert len(results) == 1
        assert isinstance(results[0], VisionStateChangeEventData)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_account(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_filters_by_project_id(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4(), project_id=uuid.uuid4())
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filters_by_entity_id(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4(), entity_id=uuid.uuid4())
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filters_by_time_range(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 12, 31, tzinfo=timezone.utc)
        results = await repo.list_by_account(uuid.uuid4(), start=start, end=end)
        assert len(results) == 1


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await repo.delete(sample_id)

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await repo.delete(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete(sample_id)
        mock_session.rollback.assert_awaited_once()


class TestGetByIdForAccount:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id_for_account(sample_id, uuid.uuid4())

        assert isinstance(data, VisionStateChangeEventData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id_for_account(uuid.uuid4(), uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id_for_account(uuid.uuid4(), uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestDeleteForAccount:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await repo.delete_for_account(sample_id, uuid.uuid4())

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await repo.delete_for_account(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete_for_account(sample_id, uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestVerifyEntityBelongsToAccount:

    @pytest.mark.asyncio
    async def test_returns_true_when_owned(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
        sample_entity_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_entity_id
        mock_session.execute.return_value = mock_result

        result = await repo.verify_entity_belongs_to_account(
            sample_entity_id, uuid.uuid4()
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_owned(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.verify_entity_belongs_to_account(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_db_error(
        self,
        repo: VisionStateChangeEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection error")

        result = await repo.verify_entity_belongs_to_account(uuid.uuid4(), uuid.uuid4())
        assert result is False
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_data_is_frozen(self) -> None:
        data = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=uuid.uuid4(),
            new_state_id=uuid.uuid4(),
            observed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            event_metadata={},
        )
        with pytest.raises(AttributeError):
            data.entity_id = uuid.uuid4()  # type: ignore[misc]
