"""Tests for the sync order repository."""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from db.repositories.order_repository import OrderRepository
from db.tables.types import IntegrationProvider


class TestCreateOrder:
    def test_inserts_order_without_dedup_lookup(self) -> None:
        session = MagicMock()
        repository = OrderRepository(session)
        display_payload = {
            "items": [{"name": "Pizza", "quantity": 1}],
            "totals": {"subtotal": "15.99"},
        }

        order_time = datetime(2026, 6, 24, 12, 30)
        order = repository.create_order(
            conversation_id=uuid.uuid4(),
            vendor=IntegrationProvider.adora,
            order_id="0",
            store_id="STORE-1",
            user_phone_number="+15551234567",
            store_phone_number="+15559876543",
            tracking_link="https://example.com/track",
            status="pending",
            fulfillment_strategy="takeout",
            subtotal=Decimal("15.99"),
            order_items=[{"name": "Pizza", "quantity": 1}],
            display_payload=display_payload,
            order_time=order_time,
        )

        assert order.vendor == IntegrationProvider.adora
        assert order.order_id == "0"
        assert order.store_id == "STORE-1"
        assert order.user_phone_number == "+15551234567"
        assert order.status == "pending"
        assert order.display_payload == display_payload
        assert order.order_time == order_time
        session.query.assert_not_called()
        session.begin_nested.assert_not_called()
        session.flush.assert_not_called()
        session.add.assert_called_once_with(order)
        session.commit.assert_called_once()

    def test_respects_auto_commit_false(self) -> None:
        session = MagicMock()
        repository = OrderRepository(session, auto_commit=False)

        order = repository.create_order(
            conversation_id=uuid.uuid4(),
            vendor=IntegrationProvider.toast,
            order_id="ORDER-123",
            store_id="STORE-1",
        )

        assert order.order_id == "ORDER-123"
        session.add.assert_called_once_with(order)
        session.commit.assert_not_called()
