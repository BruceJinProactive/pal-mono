"""Tests for db.pal_repository.ReservationRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ReservationData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.reservation import ReservationData
from db.pal_repository.reservation import ReservationRepository
from db.tables.reservations import Reservation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ReservationRepository:
    return ReservationRepository(mock_session)


@pytest.fixture
def sample_reservation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_conversation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_reservation_id: uuid.UUID,
    sample_conversation_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=Reservation)
    row.id = sample_reservation_id
    row.conversation_id = sample_conversation_id
    row.entry_type = "reservation"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.reservation_id = "ext-res-001"
    row.store_id = "store-001"
    row.tracking_link = "https://example.com/track/001"
    row.status = "confirmed"
    row.vendor = None
    row.table_size = 4
    row.special_requests = "Window seat"
    row.arrive_by_time = None
    row.expected_seating_time = None
    row.reservation_time = datetime(2025, 6, 15, 19, 0, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_reservation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_reservation_id)

        assert isinstance(data, ReservationData)
        assert data.id == sample_reservation_id
        assert data.entry_type == "reservation"
        assert data.store_id == "store-001"
        assert data.table_size == 4
        assert data.special_requests == "Window seat"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ReservationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ReservationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestGetByConversationId
# ---------------------------------------------------------------------------


class TestGetByConversationId:
    """List all reservations for a conversation."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_conversation_id(sample_conversation_id)

        assert len(results) == 1
        assert isinstance(results[0], ReservationData)
        assert results[0].conversation_id == sample_conversation_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: ReservationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_conversation_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ReservationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_conversation_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


class TestCreate:
    """Creating a new reservation."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        input_data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=sample_conversation_id,
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
            reservation_id="ext-001",
            store_id="store-new",
            status="pending",
            table_size=2,
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=sample_conversation_id,
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating reservation details."""

    @pytest.mark.asyncio
    async def test_update_commits(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_reservation_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=sample_conversation_id,
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
            status="confirmed",
            table_size=6,
        )

        await repo.update(
            reservation_id=sample_reservation_id,
            record=update_data,
        )

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_skips_when_not_found(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=sample_conversation_id,
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
            status="cancelled",
        )

        await repo.update(reservation_id=uuid.uuid4(), record=update_data)
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_only_sets_non_none_fields(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_reservation_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        # Only update status; other optional fields are None so should not
        # overwrite the existing values.
        update_data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=sample_conversation_id,
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
            status="cancelled",
        )

        await repo.update(
            reservation_id=sample_reservation_id,
            record=update_data,
        )

        # status was updated
        assert sample_orm_row.status == "cancelled"
        # table_size was NOT overwritten (still the original value from fixture)
        assert sample_orm_row.table_size == 4

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_reservation_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        update_data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=sample_conversation_id,
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
            status="fail",
        )

        with pytest.raises(SQLAlchemyError):
            await repo.update(
                reservation_id=sample_reservation_id,
                record=update_data,
            )
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a reservation."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_reservation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_reservation_id)

        assert isinstance(data, ReservationData)
        assert data.id == sample_reservation_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: ReservationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: ReservationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_reservation_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_reservation_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """ReservationData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            entry_type="reservation",
            created_at=NOW,
            updated_at=NOW,
        )
        with pytest.raises(AttributeError):
            data.status = "changed"  # type: ignore[misc]

    def test_optional_fields_default_to_none(self) -> None:
        data = ReservationData(
            id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            entry_type="reservation",
            created_at=NOW,
            updated_at=None,
        )
        assert data.reservation_id is None
        assert data.store_id is None
        assert data.tracking_link is None
        assert data.status is None
        assert data.vendor is None
        assert data.table_size is None
        assert data.special_requests is None
        assert data.arrive_by_time is None
        assert data.expected_seating_time is None
        assert data.reservation_time is None
