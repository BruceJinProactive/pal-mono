"""Tests for db.pal_repository.ToolCallRecordRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ToolCallRecordData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.tool_call_record import ToolCallRecordData
from db.pal_repository.tool_call_record import ToolCallRecordRepository, _to_data
from db.tables.tool_call_records import ToolCallRecord


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ToolCallRecordRepository:
    return ToolCallRecordRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=ToolCallRecord)
    row.id = sample_id
    row.conversation_id = uuid.uuid4()
    row.tool_name = "lookup_reservation"
    row.is_error = False
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.error_type = None
    row.duration_ms = 120
    row.result = "found"
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, ToolCallRecordData)
        assert data.id == sample_orm_row.id
        assert data.conversation_id == sample_orm_row.conversation_id
        assert data.tool_name == "lookup_reservation"
        assert data.is_error is False
        assert data.created_at == datetime(2025, 6, 1, tzinfo=timezone.utc)
        assert data.error_type is None
        assert data.duration_ms == 120
        assert data.result == "found"

    def test_converts_none_optional_fields(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.error_type = None
        sample_orm_row.duration_ms = None
        sample_orm_row.result = None
        data = _to_data(sample_orm_row)
        assert data.error_type is None
        assert data.duration_ms is None
        assert data.result is None


# ---------------------------------------------------------------------------
# ToolCallRecordData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: ToolCallRecordRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = ToolCallRecordData(
            id=sample_id,
            conversation_id=uuid.uuid4(),
            tool_name="test",
            is_error=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.tool_name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_by_conversation_id
# ---------------------------------------------------------------------------


class TestGetByConversationId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: ToolCallRecordRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_conversation_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], ToolCallRecordData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: ToolCallRecordRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_conversation_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: ToolCallRecordRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_conversation_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_record(
        self,
        repo: ToolCallRecordRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        record = ToolCallRecordData(
            id=sample_id,
            conversation_id=uuid.uuid4(),
            tool_name="lookup_reservation",
            is_error=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            duration_ms=120,
            result="found",
        )

        # After flush+refresh, the session refresh populates the row.
        # We mock ToolCallRecord constructor and make refresh a no-op
        # that keeps the mock row attributes intact.
        with patch(
            "db.pal_repository.tool_call_record.ToolCallRecord",
            return_value=sample_orm_row,
        ):
            result = await repo.create(record)

        assert isinstance(result, ToolCallRecordData)
        assert result.id == sample_id
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self,
        repo: ToolCallRecordRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        record = ToolCallRecordData(
            id=sample_id,
            conversation_id=uuid.uuid4(),
            tool_name="test",
            is_error=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        mock_session.flush.side_effect = SQLAlchemyError("db error")
        with patch(
            "db.pal_repository.tool_call_record.ToolCallRecord",
            return_value=MagicMock(spec=ToolCallRecord),
        ):
            with pytest.raises(SQLAlchemyError):
                await repo.create(record)
        mock_session.rollback.assert_awaited_once()
