"""Tests for db.pal_repository.VisionRuleEventRepository."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
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
    row.duration = Decimal("2.5000")
    row.manually_adjusted = False
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
        duration=Decimal("2.5000"),
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
        row = mock_session.add.call_args.args[0]
        assert row.duration == Decimal("2.5000")
        assert row.manually_adjusted is False
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
        assert data.duration == Decimal("2.5000")

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


class TestGetByRuleStateChangeEvent:

    @pytest.mark.asyncio
    async def test_returns_matching_event(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_rule_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_rule_state_change_event(
            rule_id=sample_rule_id,
            state_change_event_id=sample_orm_row.state_change_event_id,
        )

        assert isinstance(data, VisionRuleEventData)
        assert data.id == sample_orm_row.id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_rule_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_rule_state_change_event(
            rule_id=sample_rule_id,
            state_change_event_id=uuid.uuid4(),
        )

        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_rule_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_rule_state_change_event(
            rule_id=sample_rule_id,
            state_change_event_id=uuid.uuid4(),
        )

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
        statement = mock_session.execute.await_args.args[0]
        assert "LIMIT" not in str(statement)

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
    async def test_filters_by_manual_adjustment_state(
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

        results = await repo.list_by_account(
            uuid.uuid4(),
            manually_adjusted=True,
        )

        assert len(results) == 1
        statement = mock_session.execute.await_args.args[0]
        assert "manually_adjusted" in str(statement)

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


class TestUpdateForAccount:
    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        updated_row = MagicMock(spec=VisionRuleEvent)
        updated_row.id = sample_id
        updated_row.rule_id = sample_orm_row.rule_id
        updated_row.entity_id = sample_orm_row.entity_id
        updated_row.state_change_event_id = sample_orm_row.state_change_event_id
        updated_row.severity = sample_orm_row.severity
        updated_row.duration = Decimal("3.0000")
        updated_row.manually_adjusted = True
        updated_row.triggered_at = datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc)
        updated_row.event_metadata = sample_orm_row.event_metadata

        current_result = MagicMock()
        current_result.scalar_one_or_none.return_value = sample_orm_row
        update_result = MagicMock()
        update_result.rowcount = 1
        refreshed_result = MagicMock()
        refreshed_result.scalar_one_or_none.return_value = updated_row
        mock_session.execute.side_effect = [
            current_result,
            update_result,
            refreshed_result,
        ]

        result = await repo.update_for_account(
            event_id=sample_id,
            account_id=uuid.uuid4(),
            triggered_at=updated_row.triggered_at,
            duration=Decimal("3.0000"),
        )

        assert result is not None
        assert result.triggered_at == updated_row.triggered_at
        assert result.duration == Decimal("3.0000")
        assert result.manually_adjusted is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_event_not_found(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        current_result = MagicMock()
        current_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = current_result

        result = await repo.update_for_account(
            event_id=sample_id,
            account_id=uuid.uuid4(),
            triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration=Decimal("3.0000"),
        )

        assert result is None
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_when_update_does_not_affect_rows(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        current_result = MagicMock()
        current_result.scalar_one_or_none.return_value = sample_orm_row
        update_result = MagicMock()
        update_result.rowcount = 0
        mock_session.execute.side_effect = [current_result, update_result]

        result = await repo.update_for_account(
            event_id=sample_id,
            account_id=uuid.uuid4(),
            triggered_at=datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc),
            duration=Decimal("3.0000"),
        )

        assert result is None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionRuleEventRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("update failed")

        with pytest.raises(Exception):
            await repo.update_for_account(
                event_id=sample_id,
                account_id=uuid.uuid4(),
                triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                duration=Decimal("3.0000"),
            )
        mock_session.rollback.assert_awaited_once()
