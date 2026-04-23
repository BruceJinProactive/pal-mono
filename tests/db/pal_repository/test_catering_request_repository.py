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
    return AsyncMock()


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
    row.status = MagicMock(value="INQUIRY")
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
        assert data.status == "INQUIRY"
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
            status="INQUIRY",
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
