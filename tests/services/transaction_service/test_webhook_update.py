"""Tests for webhook-driven generic order updates."""

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Sequence
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import services.transaction_service as transaction_service
from db.repositories.order_repository import OrderRepository
from db.tables.orders import Order
from db.tables.types import IntegrationProvider
from services.transaction_service._implementation import (
    _normalize_us_phone_number,
    _parse_order_date_start,
    update_order_from_webhook,
)


class _FakeOrderRepository:
    """Fake repository for webhook update matching tests."""

    def __init__(
        self,
        external_order: SimpleNamespace | None = None,
        phone_order: SimpleNamespace | None = None,
    ) -> None:
        self.external_order = external_order
        self.phone_order = phone_order
        self.external_calls: list[dict] = []
        self.phone_calls: list[dict] = []

    def get_latest_order_by_external_ids(
        self,
        *,
        store_id: str,
        vendor: IntegrationProvider,
        order_ids: Sequence[str],
    ) -> SimpleNamespace | None:
        self.external_calls.append(
            {"store_id": store_id, "vendor": vendor, "order_ids": list(order_ids)}
        )
        return self.external_order if order_ids else None

    def get_latest_order_by_phone_since(
        self,
        *,
        store_id: str,
        vendor: IntegrationProvider,
        user_phone_number: str,
        order_time_start: datetime,
        pending_only: bool,
    ) -> SimpleNamespace | None:
        self.phone_calls.append(
            {
                "store_id": store_id,
                "vendor": vendor,
                "user_phone_number": user_phone_number,
                "order_time_start": order_time_start,
                "pending_only": pending_only,
            }
        )
        return self.phone_order if pending_only else None


def _order() -> SimpleNamespace:
    """Build an order-like object for service tests."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        order_id="ORD-789",
        store_id="STORE-1",
        user_phone_number="+15551234567",
        store_phone_number="+15559876543",
        tracking_link=None,
        status="pending",
        vendor=IntegrationProvider.adora,
        subtotal=Decimal("12.34"),
        conversation_id=uuid.uuid4(),
    )


def test_update_order_from_webhook_prefers_external_order_ids_for_non_adora() -> None:
    """Stable non-Adora webhook IDs should be tried before phone/date fallback."""
    session = MagicMock()
    order = _order()
    order.vendor = IntegrationProvider.toast
    fake_repo = _FakeOrderRepository(external_order=order)

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=fake_repo,
        ),
        patch(
            "services.transaction_service._implementation._update_customer_converted",
            return_value=True,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.toast,
            new_status="paid",
            order_id="ORD-789",
            alternate_order_id="txn-456",
            user_phone_number="5551234567",
            order_date="03/19/2026 12:30:00 PM",
            tracking_link="https://example.com/track",
        )

    assert result is not None
    assert result.id == order.id
    assert order.status == "paid"
    assert order.tracking_link == "https://example.com/track"
    assert fake_repo.external_calls[0]["order_ids"] == ["ORD-789", "txn-456"]
    assert fake_repo.phone_calls == []
    session.commit.assert_called_once()


def test_update_order_from_webhook_prefers_non_zero_adora_order_id() -> None:
    """Adora non-zero order IDs should use external-ID matching first."""
    session = MagicMock()
    order = _order()
    fake_repo = _FakeOrderRepository(external_order=order)

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=fake_repo,
        ),
        patch(
            "services.transaction_service._implementation._update_customer_converted",
            return_value=True,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            new_status="paid",
            order_id="ORD-789",
            alternate_order_id="txn-456",
            user_phone_number="5551234567",
            order_date="03/19/2026 12:30:00 PM",
        )

    assert result is not None
    assert result.id == order.id
    assert fake_repo.external_calls[0]["order_ids"] == ["ORD-789", "txn-456"]
    assert fake_repo.phone_calls == []


def test_update_order_from_webhook_falls_back_to_normalized_phone() -> None:
    """Adora non-zero order IDs should fall back to phone/date when not found."""
    session = MagicMock()
    order = _order()
    fake_repo = _FakeOrderRepository(phone_order=order)

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=fake_repo,
        ),
        patch(
            "services.transaction_service._implementation._update_customer_converted",
            return_value=True,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            new_status="paid",
            order_id="missing-order",
            alternate_order_id=None,
            user_phone_number="(555) 123-4567",
            order_date="03/19/2026 12:30:00 PM",
        )

    assert result is not None
    assert fake_repo.external_calls[0]["order_ids"] == ["missing-order"]
    assert fake_repo.phone_calls[0]["user_phone_number"] == "+15551234567"
    assert fake_repo.phone_calls[0]["pending_only"] is True
    assert fake_repo.phone_calls[0]["order_time_start"] == datetime(2026, 3, 19)


def test_update_order_from_webhook_adora_zero_order_id_uses_external_id_first() -> None:
    """Adora order ID 0 should use the same external-ID-first lookup path."""
    session = MagicMock()
    order = _order()
    order.order_id = "0"
    fake_repo = _FakeOrderRepository(
        external_order=order,
        phone_order=_order(),
    )

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=fake_repo,
        ),
        patch(
            "services.transaction_service._implementation._update_customer_converted",
            return_value=True,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            new_status="paid",
            order_id="0",
            alternate_order_id="txn-456",
            user_phone_number="(555) 123-4567",
            order_date="03/19/2026 12:30:00 PM",
        )

    assert result is not None
    assert result.id == order.id
    assert fake_repo.external_calls[0]["order_ids"] == ["0", "txn-456"]
    assert fake_repo.phone_calls == []


def test_update_order_from_webhook_returns_none_when_no_order_matches() -> None:
    """No match should return None so the webhook can raise a clear 400."""
    session = MagicMock()
    fake_repo = _FakeOrderRepository()

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=fake_repo,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            new_status="paid",
            order_id="missing-order",
            alternate_order_id=None,
            user_phone_number="5551234567",
            order_date="03/19/2026 12:30:00 PM",
        )

    assert result is None
    session.commit.assert_not_called()


def test_update_order_from_webhook_rolls_back_on_parse_error() -> None:
    """Webhook parse errors should rollback and return None."""
    session = MagicMock()
    fake_repo = _FakeOrderRepository()

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=fake_repo,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            new_status="paid",
            order_id=None,
            alternate_order_id=None,
            user_phone_number="5551234567",
            order_date=object(),
        )

    assert result is None
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_update_order_from_webhook_rolls_back_on_database_error() -> None:
    """Database errors should rollback and return None."""
    session = MagicMock()
    repository = MagicMock()
    repository.get_latest_order_by_external_ids.side_effect = SQLAlchemyError("db down")

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=repository,
        ),
    ):
        result = update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.toast,
            new_status="paid",
            order_id="ORD-789",
        )

    assert result is None
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_update_order_from_webhook_reraises_unexpected_errors() -> None:
    """Unexpected errors should surface instead of being converted to no-match."""
    session = MagicMock()
    repository = MagicMock()
    repository.get_latest_order_by_external_ids.side_effect = RuntimeError("boom")

    with (
        patch(
            "services.transaction_service._implementation.SyncSessionLocal",
            return_value=session,
        ),
        patch(
            "services.transaction_service._implementation.OrderRepository",
            return_value=repository,
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.toast,
            new_status="paid",
            order_id="ORD-789",
        )

    session.rollback.assert_not_called()
    session.close.assert_called_once()


def test_transaction_service_wrapper_delegates_webhook_update() -> None:
    """The public transaction service wrapper should delegate to implementation."""
    sentinel = object()

    with patch(
        "services.transaction_service._implementation.update_order_from_webhook",
        return_value=sentinel,
    ) as mock_update:
        result = transaction_service.update_order_from_webhook(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            new_status="paid",
            order_id="ORD-789",
            alternate_order_id="txn-456",
            user_phone_number="5551234567",
            order_date="03/19/2026 12:30:00 PM",
            tracking_link="https://example.com/track",
        )

    assert result is sentinel
    mock_update.assert_called_once_with(
        store_id="STORE-1",
        vendor=IntegrationProvider.adora,
        new_status="paid",
        order_id="ORD-789",
        alternate_order_id="txn-456",
        user_phone_number="5551234567",
        order_date="03/19/2026 12:30:00 PM",
        tracking_link="https://example.com/track",
    )


def test_normalize_us_phone_number_handles_empty_country_code_and_invalid() -> None:
    """Phone normalization supports webhook formats and rejects unusable values."""
    assert _normalize_us_phone_number(None) is None
    assert _normalize_us_phone_number("15551234567") == "+15551234567"
    assert _normalize_us_phone_number("555") is None


def test_parse_order_date_start_handles_none_datetime_and_invalid_type() -> None:
    """Date parsing should support webhook strings, datetimes, and clear failures."""
    parsed_datetime = datetime(2026, 3, 19, 12, 30)

    assert _parse_order_date_start(None) is None
    assert _parse_order_date_start(parsed_datetime) == datetime(2026, 3, 19)
    with pytest.raises(ValueError, match="order_date must be a string or datetime"):
        _parse_order_date_start(object())


def test_order_repository_external_ids_returns_none_for_empty_ids() -> None:
    """Empty external ID lists should not query the database."""
    session = MagicMock()
    repository = OrderRepository(session)

    result = repository.get_latest_order_by_external_ids(
        store_id="STORE-1",
        vendor=IntegrationProvider.adora,
        order_ids=[""],
    )

    assert result is None
    session.query.assert_not_called()


def test_order_repository_external_ids_queries_newest_matching_order() -> None:
    """External ID lookup should filter and return the newest matching order."""
    session = MagicMock()
    query = MagicMock()
    expected_order = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = expected_order
    repository = OrderRepository(session)

    result = repository.get_latest_order_by_external_ids(
        store_id="STORE-1",
        vendor=IntegrationProvider.adora,
        order_ids=["ORD-789", ""],
    )

    assert result is expected_order
    session.query.assert_called_once()
    query.filter.assert_called_once()
    query.order_by.assert_called_once()
    query.first.assert_called_once()


def test_order_repository_external_ids_rolls_back_and_reraises_db_error() -> None:
    """External ID lookup should rollback dirty sessions on database errors."""
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("db down")
    repository = OrderRepository(session)

    with pytest.raises(SQLAlchemyError):
        repository.get_latest_order_by_external_ids(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            order_ids=["ORD-789"],
        )

    session.rollback.assert_called_once()


def test_order_repository_conversation_id_queries_latest_displayable_order() -> None:
    """Conversation lookup should return the newest order with an external ID."""
    session = MagicMock()
    query = MagicMock()
    conversation_id = uuid.uuid4()
    expected_order = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        created_at=datetime(2026, 3, 19),
        order_id="ORD-789",
    )
    session.query.return_value = query
    query.with_entities.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = expected_order
    repository = OrderRepository(session)

    result = repository.get_latest_order_by_conversation_id(conversation_id)

    assert result is not None
    assert result.id == expected_order.id
    assert result.conversation_id == conversation_id
    assert result.created_at == expected_order.created_at
    assert result.order_id == "ORD-789"
    session.query.assert_called_once()
    query.with_entities.assert_called_once()
    query.filter.assert_called_once()
    query.order_by.assert_called_once()
    query.first.assert_called_once()


def test_order_repository_conversation_id_rolls_back_and_reraises_db_error() -> None:
    """Conversation lookup should rollback dirty sessions on database errors."""
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("db down")
    repository = OrderRepository(session)

    with pytest.raises(SQLAlchemyError):
        repository.get_latest_order_by_conversation_id(uuid.uuid4())

    session.rollback.assert_called_once()


def test_order_repository_conversation_ids_returns_none_for_empty_ids() -> None:
    """Empty conversation ID lists should not query the database."""
    session = MagicMock()
    repository = OrderRepository(session)

    result = repository.get_latest_orders_by_conversation_ids([])

    assert result == {}
    session.query.assert_not_called()


def test_order_repository_conversation_ids_keeps_first_order_per_conversation() -> None:
    """Batch lookup should keep the first ordered row for each conversation."""
    conversation_a = uuid.uuid4()
    conversation_b = uuid.uuid4()
    latest_a = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=conversation_a,
        created_at=datetime(2026, 3, 19),
        order_id="ORD-A2",
    )
    older_a = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=conversation_a,
        created_at=datetime(2026, 3, 18),
        order_id="ORD-A1",
    )
    latest_b = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=conversation_b,
        created_at=datetime(2026, 3, 19),
        order_id="ORD-B1",
    )
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.with_entities.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [latest_a, older_a, latest_b]
    repository = OrderRepository(session)

    result = repository.get_latest_orders_by_conversation_ids(
        [conversation_a, conversation_b]
    )

    assert set(result) == {conversation_a, conversation_b}
    assert result[conversation_a].id == latest_a.id
    assert result[conversation_a].order_id == "ORD-A2"
    assert result[conversation_b].id == latest_b.id
    assert result[conversation_b].order_id == "ORD-B1"
    session.query.assert_called_once()
    query.with_entities.assert_called_once()
    query.filter.assert_called_once()
    query.order_by.assert_called_once()
    query.all.assert_called_once()


def test_order_repository_conversation_ids_rolls_back_and_reraises_db_error() -> None:
    """Batch conversation lookup should rollback dirty sessions on database errors."""
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("db down")
    repository = OrderRepository(session)

    with pytest.raises(SQLAlchemyError):
        repository.get_latest_orders_by_conversation_ids([uuid.uuid4()])

    session.rollback.assert_called_once()


def test_order_repository_conversation_order_details_omits_order_time() -> None:
    """Order details lookup should not select order_time for admin display."""
    conversation_id = uuid.uuid4()
    expected_order = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        created_at=datetime(2026, 3, 19),
        order_id="ORD-789",
        store_id="STORE-1",
        user_phone_number="+15551234567",
        store_phone_number="+15559876543",
        tracking_link="https://example.com/track",
        status="paid",
        vendor=IntegrationProvider.adora,
        subtotal=Decimal("22.99"),
        order_items=[{"name": "Pizza", "quantity": 1}],
        fulfillment_strategy="pickup",
        updated_at=datetime(2026, 3, 19, 1, 2, 3),
    )
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.with_entities.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = expected_order
    repository = OrderRepository(session)

    result = repository.get_latest_order_details_by_conversation_id(conversation_id)

    assert result is not None
    assert result.id == expected_order.id
    assert result.conversation_id == conversation_id
    assert result.order_id == "ORD-789"
    assert result.vendor == "adora"
    assert result.order_items == ({"name": "Pizza", "quantity": 1},)
    selected_columns = query.with_entities.call_args.args
    assert all(column is not Order.order_time for column in selected_columns)
    session.query.assert_called_once()
    query.with_entities.assert_called_once()
    query.filter.assert_called_once()
    query.order_by.assert_called_once()
    query.first.assert_called_once()


def test_order_repository_conversation_order_details_rolls_back_on_db_error() -> None:
    """Order details lookup should rollback dirty sessions on database errors."""
    session = MagicMock()
    session.query.side_effect = SQLAlchemyError("db down")
    repository = OrderRepository(session)

    with pytest.raises(SQLAlchemyError):
        repository.get_latest_order_details_by_conversation_id(uuid.uuid4())

    session.rollback.assert_called_once()


def test_order_repository_phone_since_applies_pending_filter() -> None:
    """Phone/date fallback should optionally limit matches to pending orders."""
    session = MagicMock()
    query = MagicMock()
    expected_order = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = expected_order
    repository = OrderRepository(session)

    result = repository.get_latest_order_by_phone_since(
        store_id="STORE-1",
        vendor=IntegrationProvider.adora,
        user_phone_number="+15551234567",
        order_time_start=datetime(2026, 3, 19),
        pending_only=True,
    )

    assert result is expected_order
    assert query.filter.call_count == 2
    query.order_by.assert_called_once()
    query.first.assert_called_once()


def test_order_repository_phone_since_rolls_back_and_reraises_db_error() -> None:
    """Phone/date lookup should rollback dirty sessions on database errors."""
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.filter.side_effect = SQLAlchemyError("db down")
    repository = OrderRepository(session)

    with pytest.raises(SQLAlchemyError):
        repository.get_latest_order_by_phone_since(
            store_id="STORE-1",
            vendor=IntegrationProvider.adora,
            user_phone_number="+15551234567",
            order_time_start=datetime(2026, 3, 19),
            pending_only=True,
        )

    session.rollback.assert_called_once()


def test_order_repository_phone_since_can_include_non_pending_orders() -> None:
    """The second phone/date lookup should include already-updated orders."""
    session = MagicMock()
    query = MagicMock()
    expected_order = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = expected_order
    repository = OrderRepository(session)

    result = repository.get_latest_order_by_phone_since(
        store_id="STORE-1",
        vendor=IntegrationProvider.adora,
        user_phone_number="+15551234567",
        order_time_start=datetime(2026, 3, 19),
        pending_only=False,
    )

    assert result is expected_order
    query.filter.assert_called_once()
    query.order_by.assert_called_once()
    query.first.assert_called_once()
