"""Tests for db.pal_repository.CateringRequestRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only CateringRequestData instances are returned.
"""

import uuid
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.catering_request import CateringRequestRepository, _to_data
from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.tables.catering_requests import CateringRequest


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo(mock_session: AsyncMock) -> CateringRequestRepository:
    return CateringRequestRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=CateringRequest)
    row.id = sample_id
    row.project_id = uuid.uuid4()
    row.event_date = date(2025, 7, 1)
    row.contact_name = "John"
    row.contact_phone_number = "+1234567890"
    row.status = MagicMock(value="LEAD")
    row.idempotency_key = "key_123"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.event_time = time(12, 0)
    row.event_address = "123 Main St"
    row.event_detail = "Birthday party"
    row.event_fulfillment = MagicMock(value="DELIVERY")
    row.party_size = 50
    row.contact_id = uuid.uuid4()
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, CateringRequestData)
        assert data.id == sample_orm_row.id
        assert data.project_id == sample_orm_row.project_id
        assert data.event_date == date(2025, 7, 1)
        assert data.contact_name == "John"
        assert data.contact_phone_number == "+1234567890"
        assert data.status == "LEAD"
        assert data.idempotency_key == "key_123"
        assert data.event_time == time(12, 0)
        assert data.event_address == "123 Main St"
        assert data.event_detail == "Birthday party"
        assert data.event_fulfillment == "DELIVERY"
        assert data.party_size == 50
        assert data.contact_id == sample_orm_row.contact_id

    def test_converts_none_optional_fields(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.event_time = None
        sample_orm_row.event_address = None
        sample_orm_row.event_detail = None
        sample_orm_row.event_fulfillment = None
        sample_orm_row.party_size = None
        sample_orm_row.contact_id = None
        data = _to_data(sample_orm_row)
        assert data.event_time is None
        assert data.event_address is None
        assert data.event_detail is None
        assert data.event_fulfillment is None
        assert data.party_size is None
        assert data.contact_id is None

    def test_converts_none_status_to_empty_string(
        self, sample_orm_row: MagicMock
    ) -> None:
        sample_orm_row.status = None
        data = _to_data(sample_orm_row)
        assert data.status == ""


# ---------------------------------------------------------------------------
# CateringRequestData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = CateringRequestData(
            id=sample_id,
            project_id=uuid.uuid4(),
            event_date=date(2025, 7, 1),
            contact_name="John",
            contact_phone_number="+1234567890",
            status="LEAD",
            idempotency_key="key_123",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "CONFIRMED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)
        assert isinstance(data, CateringRequestData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_project_id
# ---------------------------------------------------------------------------


class TestGetByProjectId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_project_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], CateringRequestData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_project_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_project_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestListByProjectIdAndPhone:
    @pytest.mark.asyncio
    async def test_returns_matching_requests_with_normalized_phone(
        self, repo: CateringRequestRepository, sample_orm_row: MagicMock
    ) -> None:
        matching = _to_data(sample_orm_row)
        non_matching = CateringRequestData(
            id=uuid.uuid4(),
            project_id=sample_orm_row.project_id,
            event_date=date(2025, 7, 2),
            contact_name="Jane",
            contact_phone_number="+19876543210",
            status="LEAD",
            idempotency_key="key_456",
            created_at=sample_orm_row.created_at,
            updated_at=sample_orm_row.updated_at,
        )
        repo.get_by_project_id = AsyncMock(  # type: ignore[method-assign]
            return_value=[matching, non_matching]
        )

        results = await repo.list_by_project_id_and_phone(
            sample_orm_row.project_id,
            "(123) 456-7890",
        )

        assert results == [matching]

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_blank_phone(
        self, repo: CateringRequestRepository
    ) -> None:
        repo.get_by_project_id = AsyncMock()  # type: ignore[method-assign]

        results = await repo.list_by_project_id_and_phone(uuid.uuid4(), "")

        assert results == []
        repo.get_by_project_id.assert_not_called()


# ---------------------------------------------------------------------------
# get_by_idempotency_key
# ---------------------------------------------------------------------------


class TestGetByIdempotencyKey:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_idempotency_key("key_123")
        assert isinstance(data, CateringRequestData)
        assert data.idempotency_key == "key_123"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_idempotency_key("nonexistent") is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_idempotency_key("key_123")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_request(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        persisted_id = uuid.uuid4()
        data = CateringRequestData(
            id=sample_id,
            project_id=uuid.uuid4(),
            event_date=date(2025, 7, 1),
            contact_name="John",
            contact_phone_number="+1234567890",
            status="LEAD",
            idempotency_key="key_123",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            event_time=time(12, 0),
            party_size=50,
        )

        async def assign_persisted_id() -> None:
            row = mock_session.add.call_args.args[0]
            row.id = persisted_id

        mock_session.flush.side_effect = assign_persisted_id

        result = await repo.create(data)

        assert result == persisted_id
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")
        data = CateringRequestData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            event_date=date(2025, 7, 1),
            contact_name="John",
            contact_phone_number="+1234567890",
            status="LEAD",
            idempotency_key="key_456",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(Exception, match="insert failed"):
            await repo.create(data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_fields_and_returns_data(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        data = await repo.update(
            idempotency_key="key_123",
            contact_name="Jane",
            party_size=100,
        )
        assert isinstance(data, CateringRequestData)
        # execute called 3 times: get_by_idempotency_key, update stmt, get_by_idempotency_key again
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.update(idempotency_key="unknown_key", contact_name="Jane")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_commit_when_no_fields_provided(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        await repo.update(idempotency_key="key_123")
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError):
            await repo.update(idempotency_key="unknown_key", contact_name="Jane")
        mock_session.rollback.assert_awaited_once()
