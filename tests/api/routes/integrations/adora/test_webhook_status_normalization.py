# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for Adora webhook status normalization.

Tests cover:
- Status normalization when Event == "Paid" -> "paid"
- Status normalization for non-Paid events (passthrough)
- update_order_by_phone called with normalized status
- order.status set to normalized value
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.integrations.adora._utils import update_order_status
from api.routes.integrations.adora.schemas import AdoraWebhookRequest
from db.tables.adora_orders import AdoraOrder
from db.tables.types import IntegrationProvider

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def webhook_request_paid() -> AdoraWebhookRequest:
    """Create a webhook request with Event == 'Paid'."""
    return AdoraWebhookRequest(
        Event="Paid",
        storeId="test-store-123",
        PhoneNumber="5551234567",
        transactionId="txn-456",
        OrderNumber="ORD-789",
        OrderDate="03/19/2026 12:30:00 PM",
        trackingLink="https://example.com/track/123",
        brandId=None,
    )


@pytest.fixture
def webhook_request_ready() -> AdoraWebhookRequest:
    """Create a webhook request with Event == 'Ready to pick up'."""
    return AdoraWebhookRequest(
        Event="Ready to pick up",
        storeId="test-store-123",
        PhoneNumber="5551234567",
        transactionId="txn-456",
        OrderNumber="ORD-789",
        OrderDate="03/19/2026 12:30:00 PM",
        trackingLink=None,
        brandId=None,
    )


@pytest.fixture
def webhook_request_delivered() -> AdoraWebhookRequest:
    """Create a webhook request with Event == 'Delivered'."""
    return AdoraWebhookRequest(
        Event="Delivered",
        storeId="test-store-123",
        PhoneNumber="5551234567",
        transactionId="txn-456",
        OrderNumber="ORD-789",
        OrderDate="03/19/2026 12:30:00 PM",
        trackingLink=None,
        brandId=None,
    )


@pytest.fixture
def mock_adora_order() -> AdoraOrder:
    """Create a mock AdoraOrder with pending status."""
    order = AdoraOrder()
    order.id = uuid.uuid4()
    order.user_phone_number = "+15551234567"
    order.store_phone_number = "+15559876543"
    order.order_number = "ORD-789"
    order.transaction_id = "txn-456"
    order.store_id = "test-store-123"
    order.tracking_link = None
    order.status = "pending"
    order.vendor = IntegrationProvider.adora
    order.order_date = datetime(2026, 3, 19, 12, 30, 0)
    order.created_at = datetime(2026, 3, 19, 12, 25, 0)
    order.updated_at = datetime(2026, 3, 19, 12, 25, 0)
    return order


# ---------------------------------------------------------------------------
# Status Normalization Tests
# ---------------------------------------------------------------------------


class TestUpdateOrderStatusNormalization:
    """Test status normalization in update_order_status function."""

    @pytest.mark.asyncio
    async def test_paid_event_normalizes_to_lowercase(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
        mock_adora_order: AdoraOrder,
    ) -> None:
        """When Event == 'Paid', order.status should be set to 'paid' (lowercase)."""
        # Mock the database query to return a single order
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_adora_order]
        mock_session.execute.return_value = mock_result

        # Mock update_order_by_phone
        with patch(
            "api.routes.integrations.adora._utils.update_order_by_phone"
        ) as mock_update:
            mock_update.return_value = True

            # Call the function
            result = await update_order_status(mock_session, webhook_request_paid)

            # Assert order.status was set to lowercase "paid"
            assert result.status == "paid", f"Expected 'paid', got '{result.status}'"
            assert result.status != "Paid", "Status should not be capitalized 'Paid'"

    @pytest.mark.asyncio
    async def test_paid_event_calls_update_with_lowercase(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
        mock_adora_order: AdoraOrder,
    ) -> None:
        """When Event == 'Paid', update_order_by_phone should be called with new_status='paid'."""
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_adora_order]
        mock_session.execute.return_value = mock_result

        # Mock update_order_by_phone and capture its call
        with patch(
            "api.routes.integrations.adora._utils.update_order_by_phone"
        ) as mock_update:
            mock_update.return_value = True

            # Call the function
            await update_order_status(mock_session, webhook_request_paid)

            # Assert update_order_by_phone was called with normalized status
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert (
                call_kwargs["new_status"] == "paid"
            ), f"Expected new_status='paid', got '{call_kwargs['new_status']}'"
            assert call_kwargs["vendor"] == IntegrationProvider.adora
            assert call_kwargs["store_id"] == "test-store-123"

    @pytest.mark.asyncio
    async def test_non_paid_event_passthrough(
        self,
        mock_session: AsyncMock,
        webhook_request_ready: AdoraWebhookRequest,
        mock_adora_order: AdoraOrder,
    ) -> None:
        """Non-'Paid' events should pass through unchanged to order.status."""
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_adora_order]
        mock_session.execute.return_value = mock_result

        # Mock update_order_by_phone
        with patch(
            "api.routes.integrations.adora._utils.update_order_by_phone"
        ) as mock_update:
            mock_update.return_value = True

            # Call the function
            result = await update_order_status(mock_session, webhook_request_ready)

            # Assert order.status was set to the original Event value
            assert (
                result.status == "Ready to pick up"
            ), f"Expected 'Ready to pick up', got '{result.status}'"

    @pytest.mark.asyncio
    async def test_non_paid_event_calls_update_with_original(
        self,
        mock_session: AsyncMock,
        webhook_request_delivered: AdoraWebhookRequest,
        mock_adora_order: AdoraOrder,
    ) -> None:
        """Non-'Paid' events should call update_order_by_phone with original Event."""
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_adora_order]
        mock_session.execute.return_value = mock_result

        # Mock update_order_by_phone and capture its call
        with patch(
            "api.routes.integrations.adora._utils.update_order_by_phone"
        ) as mock_update:
            mock_update.return_value = True

            # Call the function
            await update_order_status(mock_session, webhook_request_delivered)

            # Assert update_order_by_phone was called with original event string
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert (
                call_kwargs["new_status"] == "Delivered"
            ), f"Expected new_status='Delivered', got '{call_kwargs['new_status']}'"

    @pytest.mark.asyncio
    async def test_tracking_link_updated(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
        mock_adora_order: AdoraOrder,
    ) -> None:
        """Tracking link should be updated when provided in webhook."""
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_adora_order]
        mock_session.execute.return_value = mock_result

        # Mock update_order_by_phone
        with patch(
            "api.routes.integrations.adora._utils.update_order_by_phone"
        ) as mock_update:
            mock_update.return_value = True

            # Call the function
            result = await update_order_status(mock_session, webhook_request_paid)

            # Assert tracking link was updated
            assert (
                result.tracking_link == "https://example.com/track/123"
            ), f"Expected tracking link to be updated, got '{result.tracking_link}'"

    @pytest.mark.asyncio
    async def test_multiple_orders_uses_first(
        self, mock_session: AsyncMock, webhook_request_paid: AdoraWebhookRequest
    ) -> None:
        """When multiple orders match, the first one should be updated."""
        # Create multiple mock orders
        order1 = AdoraOrder()
        order1.id = uuid.uuid4()
        order1.status = "pending"
        order1.user_phone_number = "+15551234567"
        order1.store_id = "test-store-123"
        order1.order_number = "ORD-001"
        order1.transaction_id = "txn-001"

        order2 = AdoraOrder()
        order2.id = uuid.uuid4()
        order2.status = "pending"
        order2.user_phone_number = "+15551234567"
        order2.store_id = "test-store-123"
        order2.order_number = "ORD-002"
        order2.transaction_id = "txn-002"

        # Mock the database query to return multiple orders
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [order1, order2]
        mock_session.execute.return_value = mock_result

        # Mock update_order_by_phone
        with patch(
            "api.routes.integrations.adora._utils.update_order_by_phone"
        ) as mock_update:
            mock_update.return_value = True

            # Call the function
            result = await update_order_status(mock_session, webhook_request_paid)

            # Assert the first order was updated
            assert result.id == order1.id, "Expected first order to be returned"
            assert result.status == "paid", "Expected status to be normalized to 'paid'"
