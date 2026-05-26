"""Tests for db.pal_repository.VisionRuleEventRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from db.pal_repository.vision_rule_event import VisionRuleEventRepository
from db.tables.vision_rule_events import VisionRuleEvent


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionRuleEventRepository:
    return VisionRuleEventRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_rule_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID, sample_rule_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=VisionRuleEvent)
    row.id = sample_id
    row.rule_id = sample_rule_id
    row.entity_id = uuid.uuid4()
    row.state_change_event_id = uuid.uuid4()
    row.severity = "high"
    row.triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    row.event_metadata = {"detail": "dirty"}
    return row


@pytest.fixture
def sample_data(sample_id: uuid.UUID, sample_rule_id: uuid.UUID) -> VisionRuleEventData:
    return VisionRuleEventData(
        id=sample_id,
        rule_id=sample_rule_id,
        entity_id=uuid.uuid4(),
        state_change_event_id=uuid.uuid4(),
        severity="high",
        triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        event_metadata={"detail": "dirty"},
    )


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_data: VisionRuleEventData,
    ) -> None:
        await repo.create(sample_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_data: VisionRuleEventData,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        with pytest.raises(Exception):
            await repo.create(sample_data)
        mock_session.rollback.assert_awaited_once()


class TestGetByIdForAccount:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id_for_account(sample_id, uuid.uuid4())

        assert isinstance(data, VisionRuleEventData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: VisionRuleEventRepository,
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
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id_for_account(uuid.uuid4(), uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestListByAccount:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4())

        assert len(results) == 1
        assert isinstance(results[0], VisionRuleEventData)

    @pytest.mark.asyncio
    async def test_filters_by_rule_id(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4(), rule_id=uuid.uuid4())
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filters_by_entity_id(
        self,
        repo: VisionRuleEventRepository,
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
        repo: VisionRuleEventRepository,
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

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_account(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()


class TestDeleteForAccount:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionRuleEventRepository,
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
        repo: VisionRuleEventRepository,
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
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete_for_account(sample_id, uuid.uuid4())
        mock_session.rollback.assert_awaited_once()
