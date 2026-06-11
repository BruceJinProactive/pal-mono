"""Tests for db.pal_repository.OrderRepository.

Validates the async repository: ORM objects stay inside the repository layer and
only data-class snapshots are returned.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.order import (
    LatestOrderData,
    OrderCustomerHistoryData,
    OrderData,
    OrderDetailsData,
)
from db.pal_repository.order import OrderRepository, _to_data
from db.tables.orders import Order


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> OrderRepository:
    return OrderRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=Order)
    row.id = sample_id
    row.conversation_id = uuid.uuid4()
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.order_id = "ORD-001"
    row.idempotency_key = "order:external:v1:toast:STORE-1:ORD-001"
    row.store_id = "STORE-1"
    row.user_phone_number = "+15551234567"
    row.store_phone_number = "+15559876543"
    row.tracking_link = "https://track.example.com/ORD-001"
    row.status = "confirmed"
    row.vendor = MagicMock(value="Toast")
    row.subtotal = Decimal("29.99")
    row.order_items = [{"name": "Pizza", "qty": 1}]
    row.fulfillment_strategy = "delivery"
    row.order_time = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, 12, 5, tzinfo=timezone.utc)
    return row


def _make_order_row(conversation_id: uuid.UUID, order_id: str) -> MagicMock:
    row = MagicMock(spec=Order)
    row.id = uuid.uuid4()
    row.conversation_id = conversation_id
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.order_id = order_id
    row.store_id = "STORE-1"
    row.user_phone_number = "+15551234567"
    row.store_phone_number = "+15559876543"
    row.tracking_link = None
    row.status = "confirmed"
    row.vendor = None
    row.subtotal = Decimal("29.99")
    row.order_items = []
    row.fulfillment_strategy = "pickup"
    row.order_time = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, 12, 5, tzinfo=timezone.utc)
    return row


def _make_latest_order_mapping(row: MagicMock) -> dict[str, object]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "created_at": row.created_at,
        "order_id": row.order_id,
    }


def _make_order_details_mapping(row: MagicMock) -> dict[str, object]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "created_at": row.created_at,
        "order_id": row.order_id,
        "store_id": row.store_id,
        "user_phone_number": row.user_phone_number,
        "store_phone_number": row.store_phone_number,
        "tracking_link": row.tracking_link,
        "status": row.status,
        "vendor": row.vendor,
        "subtotal": row.subtotal,
        "order_items": row.order_items,
        "fulfillment_strategy": row.fulfillment_strategy,
        "updated_at": row.updated_at,
    }


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, OrderData)
        assert data.id == sample_orm_row.id
        assert data.conversation_id == sample_orm_row.conversation_id
        assert data.order_id == "ORD-001"
        assert data.idempotency_key == "order:external:v1:toast:STORE-1:ORD-001"
        assert data.store_id == "STORE-1"
        assert data.user_phone_number == "+15551234567"
        assert data.store_phone_number == "+15559876543"
        assert data.tracking_link == "https://track.example.com/ORD-001"
        assert data.status == "confirmed"
        assert data.vendor == "Toast"
        assert data.subtotal == Decimal("29.99")
        assert isinstance(data.order_items, tuple)
        assert len(data.order_items) == 1
        assert data.fulfillment_strategy == "delivery"

    def test_converts_none_vendor(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.vendor = None
        data = _to_data(sample_orm_row)
        assert data.vendor is None

    def test_converts_none_order_items(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.order_items = None
        data = _to_data(sample_orm_row)
        assert data.order_items == ()

    def test_converts_empty_order_items(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.order_items = []
        data = _to_data(sample_orm_row)
        assert data.order_items == ()


# ---------------------------------------------------------------------------
# OrderData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = OrderData(
            id=sample_id,
            conversation_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "cancelled"  # type: ignore[misc]

    def test_order_items_is_tuple(self, sample_id: uuid.UUID) -> None:
        data = OrderData(
            id=sample_id,
            conversation_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            order_items=({"name": "Pizza"},),
        )
        assert isinstance(data.order_items, tuple)


# ---------------------------------------------------------------------------
# get_customer_history_by_project_id_and_phone
# ---------------------------------------------------------------------------


class TestGetCustomerHistoryByProjectIdAndPhone:
    @pytest.mark.asyncio
    async def test_returns_history_summary(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        last_order_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one.return_value = {
            "order_count": 3,
            "last_order_at": last_order_at,
        }
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        result = await repo.get_customer_history_by_project_id_and_phone(
            uuid.uuid4(),
            "(555) 123-4567",
        )

        assert isinstance(result, OrderCustomerHistoryData)
        assert result.order_count == 3
        assert result.last_order_at == last_order_at
        mock_session.execute.assert_awaited_once()
        statement_text = str(mock_session.execute.call_args.args[0])
        assert "JOIN conversations" in statement_text
        assert "JOIN projects" in statement_text
        assert "account_id" in statement_text
        assert "regexp_replace" in statement_text

    @pytest.mark.asyncio
    async def test_blank_phone_skips_query(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        result = await repo.get_customer_history_by_project_id_and_phone(
            uuid.uuid4(),
            "",
        )

        assert result.order_count == 0
        assert result.last_order_at is None
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_customer_history_by_project_id_and_phone(
                uuid.uuid4(),
                "+15551234567",
            )
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: OrderRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)
        assert isinstance(data, OrderData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_idempotency_key
# ---------------------------------------------------------------------------


class TestGetByIdempotencyKey:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: OrderRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_idempotency_key(
            "order:external:v1:toast:STORE-1:ORD-001"
        )

        assert isinstance(data, OrderData)
        assert data.idempotency_key == "order:external:v1:toast:STORE-1:ORD-001"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_idempotency_key("missing-key") is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_idempotency_key("order:external:v1:toast:STORE-1:ORD-001")

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_conversation_id
# ---------------------------------------------------------------------------


class TestGetByConversationId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: OrderRepository,
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
        assert isinstance(results[0], OrderData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: OrderRepository, mock_session: AsyncMock
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
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_conversation_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_latest_order_by_conversation_id
# ---------------------------------------------------------------------------


class TestGetLatestOrderByConversationId:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: OrderRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one_or_none.return_value = _make_latest_order_mapping(
            sample_orm_row
        )
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        data = await repo.get_latest_order_by_conversation_id(uuid.uuid4())

        assert isinstance(data, LatestOrderData)
        assert data.order_id == "ORD-001"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one_or_none.return_value = None
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        assert await repo.get_latest_order_by_conversation_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_latest_order_by_conversation_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_latest_orders_by_conversation_ids
# ---------------------------------------------------------------------------


class TestGetLatestOrdersByConversationIds:
    @pytest.mark.asyncio
    async def test_returns_first_order_per_conversation(
        self,
        repo: OrderRepository,
        mock_session: AsyncMock,
    ) -> None:
        conversation_a = uuid.uuid4()
        conversation_b = uuid.uuid4()
        latest_a = _make_order_row(conversation_a, "ORD-A2")
        older_a = _make_order_row(conversation_a, "ORD-A1")
        latest_b = _make_order_row(conversation_b, "ORD-B1")
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = [
            _make_latest_order_mapping(latest_a),
            _make_latest_order_mapping(older_a),
            _make_latest_order_mapping(latest_b),
        ]
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        results = await repo.get_latest_orders_by_conversation_ids(
            [conversation_a, conversation_b]
        )

        assert set(results) == {conversation_a, conversation_b}
        assert isinstance(results[conversation_a], LatestOrderData)
        assert results[conversation_a].order_id == "ORD-A2"
        assert results[conversation_b].order_id == "ORD-B1"

    @pytest.mark.asyncio
    async def test_empty_ids_skip_query(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        results = await repo.get_latest_orders_by_conversation_ids([])

        assert results == {}
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_latest_orders_by_conversation_ids([uuid.uuid4()])
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_latest_order_details_by_conversation_id
# ---------------------------------------------------------------------------


class TestGetLatestOrderDetailsByConversationId:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: OrderRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one_or_none.return_value = _make_order_details_mapping(
            sample_orm_row
        )
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        data = await repo.get_latest_order_details_by_conversation_id(uuid.uuid4())

        assert isinstance(data, OrderDetailsData)
        assert data.order_id == "ORD-001"
        assert data.vendor == "Toast"
        assert data.order_items == ({"name": "Pizza", "qty": 1},)
        statement = mock_session.execute.call_args.args[0]
        selected_keys = {column.key for column in statement.selected_columns}
        assert "order_time" not in selected_keys

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.one_or_none.return_value = None
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute.return_value = mock_result

        assert (
            await repo.get_latest_order_details_by_conversation_id(uuid.uuid4()) is None
        )

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: OrderRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_latest_order_details_by_conversation_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()
