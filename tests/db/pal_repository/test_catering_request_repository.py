"""Tests for db.pal_repository.CateringRequestRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only CateringRequestData instances are returned.
"""

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.catering_request import (
    CateringRequestRepository,
    _phone_match_keys,
    _to_data,
)
from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.tables.catering_requests import CateringRequest


def _catering_request_data(
    sample_orm_row: MagicMock,
    *,
    request_id: uuid.UUID | None = None,
    contact_phone_number: str | None = None,
) -> CateringRequestData:
    return CateringRequestData(
        id=request_id or uuid.uuid4(),
        project_id=sample_orm_row.project_id,
        event_date=sample_orm_row.event_date,
        contact_name=sample_orm_row.contact_name,
        contact_phone_number=contact_phone_number,
        contact_email=sample_orm_row.contact_email,
        status="LEAD",
        idempotency_key=f"key_{request_id or uuid.uuid4()}",
        created_at=sample_orm_row.created_at,
        updated_at=sample_orm_row.updated_at,
        event_time=sample_orm_row.event_time,
        event_address=sample_orm_row.event_address,
        event_detail=sample_orm_row.event_detail,
        all_items=sample_orm_row.all_items,
        event_fulfillment="DELIVERY",
        party_size=sample_orm_row.party_size,
        contact_id=sample_orm_row.contact_id,
    )


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
    row.contact_email = "john@example.com"
    row.status = MagicMock(value="LEAD")
    row.idempotency_key = "key_123"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.prior_catering_request_count = 2
    row.prior_order_count = 3
    row.last_catering_request_at = datetime(2025, 5, 1, tzinfo=timezone.utc)
    row.last_order_at = datetime(2025, 5, 15, tzinfo=timezone.utc)
    row.estimated_order_value = Decimal("500.00")
    row.confirmed_order_value = Decimal("525.00")
    row.deposit_requirement_value = Decimal("100.00")
    row.deposit_received_value = Decimal("50.00")
    row.event_time = time(12, 0)
    row.event_address = "123 Main St"
    row.event_detail = "Birthday party"
    row.all_items = {"Cake tray": {"quantity": 2, "price": 80.00}}
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
        assert data.contact_email == "john@example.com"
        assert data.status == "LEAD"
        assert data.idempotency_key == "key_123"
        assert data.prior_catering_request_count == 2
        assert data.prior_order_count == 3
        assert data.last_catering_request_at == datetime(
            2025, 5, 1, tzinfo=timezone.utc
        )
        assert data.last_order_at == datetime(2025, 5, 15, tzinfo=timezone.utc)
        assert data.estimated_order_value == Decimal("500.00")
        assert data.confirmed_order_value == Decimal("525.00")
        assert data.deposit_requirement_value == Decimal("100.00")
        assert data.deposit_received_value == Decimal("50.00")
        assert data.event_time == time(12, 0)
        assert data.event_address == "123 Main St"
        assert data.event_detail == "Birthday party"
        assert data.all_items == {"Cake tray": {"quantity": 2, "price": 80.00}}
        assert data.event_fulfillment == "DELIVERY"
        assert data.party_size == 50
        assert data.contact_id == sample_orm_row.contact_id

    def test_converts_none_optional_fields(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.event_time = None
        sample_orm_row.event_address = None
        sample_orm_row.event_detail = None
        sample_orm_row.all_items = None
        sample_orm_row.event_fulfillment = None
        sample_orm_row.event_date = None
        sample_orm_row.party_size = None
        sample_orm_row.contact_id = None
        sample_orm_row.contact_phone_number = None
        sample_orm_row.contact_email = None
        data = _to_data(sample_orm_row)
        assert data.event_time is None
        assert data.event_address is None
        assert data.event_detail is None
        assert data.event_fulfillment is None
        assert data.event_date is None
        assert data.party_size is None
        assert data.contact_id is None
        assert data.contact_phone_number is None
        assert data.contact_email is None

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
    def test_phone_match_keys_matches_us_number_with_or_without_country_code(
        self,
    ) -> None:
        assert _phone_match_keys("1234567890") == {"1234567890", "11234567890"}
        assert _phone_match_keys("+1 (123) 456-7890") == {
            "1234567890",
            "11234567890",
        }

    @pytest.mark.asyncio
    async def test_returns_matching_requests_with_normalized_phone(
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

        results = await repo.list_by_project_id_and_phone(
            sample_orm_row.project_id,
            "(123) 456-7890",
        )

        assert len(results) == 1
        assert results[0].id == sample_orm_row.id
        executed_statement = mock_session.execute.await_args.args[0]
        statement_sql = str(executed_statement)
        assert "regexp_replace" in statement_sql
        assert "contact_phone_number" in statement_sql
        assert "project_id" in statement_sql
        assert "created_at DESC" in statement_sql

    @pytest.mark.asyncio
    async def test_queries_database_for_country_code_variant(
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

        bare_results = await repo.list_by_project_id_and_phone(
            sample_orm_row.project_id,
            "1234567890",
        )
        country_code_results = await repo.list_by_project_id_and_phone(
            sample_orm_row.project_id,
            "+11234567890",
        )

        assert [result.id for result in bare_results] == [sample_orm_row.id]
        assert [result.id for result in country_code_results] == [sample_orm_row.id]
        assert mock_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_blank_phone(
        self, repo: CateringRequestRepository
    ) -> None:
        repo.get_by_project_id = AsyncMock()  # type: ignore[method-assign]

        results = await repo.list_by_project_id_and_phone(uuid.uuid4(), "")

        assert results == []
        repo.get_by_project_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_project_id_and_phone(uuid.uuid4(), "(123) 456-7890")

        mock_session.rollback.assert_awaited_once()


class TestGetCustomerHistoryByProjectIdAndPhoneOrEmail:
    @pytest.mark.asyncio
    async def test_returns_history_summary(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        last_request_at = datetime(2025, 5, 1, tzinfo=timezone.utc)
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one.return_value = {
            "request_count": 2,
            "last_request_at": last_request_at,
        }
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        result = await repo.get_customer_history_by_project_id_and_phone_or_email(
            uuid.uuid4(),
            "(123) 456-7890",
            "John@Example.COM ",
        )

        assert result.request_count == 2
        assert result.last_request_at == last_request_at
        mock_session.execute.assert_awaited_once()
        statement = mock_session.execute.call_args.args[0]
        statement_text = str(statement)
        assert "JOIN projects" in statement_text
        assert "account_id" in statement_text
        assert "regexp_replace" in statement_text
        assert "lower(trim(coalesce(catering_requests.contact_email" in statement_text
        assert " OR " in statement_text

    @pytest.mark.asyncio
    async def test_email_only_runs_history_query(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        last_request_at = datetime(2025, 5, 1, tzinfo=timezone.utc)
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one.return_value = {
            "request_count": 1,
            "last_request_at": last_request_at,
        }
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        result = await repo.get_customer_history_by_project_id_and_phone_or_email(
            uuid.uuid4(),
            None,
            "John@Example.COM ",
        )

        assert result.request_count == 1
        assert result.last_request_at == last_request_at
        mock_session.execute.assert_awaited_once()
        statement_text = str(mock_session.execute.call_args.args[0])
        assert "lower(trim(coalesce(catering_requests.contact_email" in statement_text
        assert "regexp_replace" not in statement_text

    @pytest.mark.asyncio
    async def test_blank_phone_and_email_skip_query(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        result = await repo.get_customer_history_by_project_id_and_phone_or_email(
            uuid.uuid4(),
            "",
            " ",
        )

        assert result.request_count == 0
        assert result.last_request_at is None
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: CateringRequestRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_customer_history_by_project_id_and_phone_or_email(
                uuid.uuid4(),
                "+1234567890",
                "john@example.com",
            )
        mock_session.rollback.assert_awaited_once()


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
            contact_email="john@example.com",
            status="LEAD",
            idempotency_key="key_123",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            prior_catering_request_count=2,
            prior_order_count=3,
            last_catering_request_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            last_order_at=datetime(2025, 5, 15, tzinfo=timezone.utc),
            estimated_order_value=Decimal("500.00"),
            confirmed_order_value=Decimal("525.00"),
            deposit_requirement_value=Decimal("100.00"),
            deposit_received_value=Decimal("50.00"),
            event_time=time(12, 0),
            all_items={"Cake tray": {"quantity": 2, "price": 80.00}},
            party_size=50,
        )

        async def assign_persisted_id() -> None:
            row = mock_session.add.call_args.args[0]
            row.id = persisted_id

        mock_session.flush.side_effect = assign_persisted_id

        result = await repo.create(data)

        assert result == persisted_id
        row = mock_session.add.call_args.args[0]
        if hasattr(row, "all_items"):
            assert row.all_items == {"Cake tray": {"quantity": 2, "price": 80.00}}
        mock_session.add.assert_called_once()
        added_row = mock_session.add.call_args.args[0]
        assert added_row.contact_email == "john@example.com"
        assert row.prior_catering_request_count == 2
        assert row.prior_order_count == 3
        assert row.last_catering_request_at == datetime(2025, 5, 1, tzinfo=timezone.utc)
        assert row.last_order_at == datetime(2025, 5, 15, tzinfo=timezone.utc)
        assert row.estimated_order_value == Decimal("500.00")
        assert row.confirmed_order_value == Decimal("525.00")
        assert row.deposit_requirement_value == Decimal("100.00")
        assert row.deposit_received_value == Decimal("50.00")
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
            contact_email="john@example.com",
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
            contact_email=None,
            all_items={"Sandwich platter": {"quantity": 3, "price": 150.00}},
            party_size=100,
            estimated_order_value=Decimal("600.00"),
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


# ---------------------------------------------------------------------------
# delete_by_id
# ---------------------------------------------------------------------------


class TestDeleteById:
    @pytest.mark.asyncio
    async def test_deletes_existing_request(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        existing = _to_data(sample_orm_row)
        repo.get_by_id = AsyncMock(return_value=existing)  # type: ignore[method-assign]

        result = await repo.delete_by_id(sample_id)

        assert result == existing
        repo.get_by_id.assert_awaited_once_with(sample_id)
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_request_missing(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        repo.get_by_id = AsyncMock(return_value=None)  # type: ignore[method-assign]

        result = await repo.delete_by_id(sample_id)

        assert result is None
        mock_session.execute.assert_not_awaited()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self,
        repo: CateringRequestRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        repo.get_by_id = AsyncMock(  # type: ignore[method-assign]
            return_value=_to_data(sample_orm_row)
        )
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            await repo.delete_by_id(sample_id)

        mock_session.rollback.assert_awaited_once()
