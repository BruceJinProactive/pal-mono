"""Tests for Adora webhook status normalization and generic order updates."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.integrations.adora._utils import (
    _generate_notification_text,
    send_order_notification,
    update_order_status,
)
from api.routes.integrations.adora.schemas import AdoraWebhookRequest
from db.tables.types import IntegrationProvider
from services.transaction_service import OrderStatusUpdateResult


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession."""
    return AsyncMock(spec=AsyncSession)


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


def _order_result(
    *,
    order_id: str | None = "ORD-789",
    status: str = "paid",
    tracking_link: str | None = None,
    user_phone_number: str | None = "+15551234567",
    store_phone_number: str | None = "+15559876543",
) -> OrderStatusUpdateResult:
    """Build an updated order snapshot for webhook tests."""
    return OrderStatusUpdateResult(
        id=uuid.uuid4(),
        order_id=order_id,
        store_id="test-store-123",
        user_phone_number=user_phone_number,
        store_phone_number=store_phone_number,
        tracking_link=tracking_link,
        status=status,
        vendor=IntegrationProvider.adora,
    )


class TestUpdateOrderStatusNormalization:
    """Test status normalization in update_order_status."""

    @pytest.mark.asyncio
    async def test_paid_event_normalizes_to_lowercase(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
    ) -> None:
        """When Event == 'Paid', order.status should be lowercase."""
        with patch(
            "api.routes.integrations.adora._utils.update_order_from_webhook",
            return_value=_order_result(status="paid"),
        ):
            result = await update_order_status(mock_session, webhook_request_paid)

        assert result.status == "paid"

    @pytest.mark.asyncio
    async def test_paid_event_calls_update_with_identifiers(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
    ) -> None:
        """Paid webhooks should update generic orders by stable IDs first."""
        with patch(
            "api.routes.integrations.adora._utils.update_order_from_webhook",
            return_value=_order_result(status="paid"),
        ) as mock_update:
            await update_order_status(mock_session, webhook_request_paid)

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["new_status"] == "paid"
        assert call_kwargs["vendor"] == IntegrationProvider.adora
        assert call_kwargs["store_id"] == "test-store-123"
        assert call_kwargs["order_id"] == "ORD-789"
        assert call_kwargs["alternate_order_id"] == "txn-456"
        assert call_kwargs["user_phone_number"] == "5551234567"

    @pytest.mark.asyncio
    async def test_non_paid_event_passthrough(
        self,
        mock_session: AsyncMock,
        webhook_request_ready: AdoraWebhookRequest,
    ) -> None:
        """Non-'Paid' events should pass through unchanged."""
        with patch(
            "api.routes.integrations.adora._utils.update_order_from_webhook",
            return_value=_order_result(status="Ready to pick up"),
        ):
            result = await update_order_status(mock_session, webhook_request_ready)

        assert result.status == "Ready to pick up"

    @pytest.mark.asyncio
    async def test_tracking_link_forwarded(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
    ) -> None:
        """Tracking link should be forwarded to the generic order updater."""
        with patch(
            "api.routes.integrations.adora._utils.update_order_from_webhook",
            return_value=_order_result(
                status="paid",
                tracking_link="https://example.com/track/123",
            ),
        ) as mock_update:
            result = await update_order_status(mock_session, webhook_request_paid)

        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["tracking_link"] == "https://example.com/track/123"
        assert result.tracking_link == "https://example.com/track/123"

    @pytest.mark.asyncio
    async def test_missing_generic_order_raises_value_error(
        self,
        mock_session: AsyncMock,
        webhook_request_paid: AdoraWebhookRequest,
    ) -> None:
        """Webhook fails clearly when no generic order can be matched."""
        with patch(
            "api.routes.integrations.adora._utils.update_order_from_webhook",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Order not found in orders table"):
                await update_order_status(mock_session, webhook_request_paid)

    @pytest.mark.asyncio
    async def test_missing_event_raises_value_error(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Webhook status updates require an event value."""
        webhook_request = AdoraWebhookRequest.model_construct(
            Event=None,
            storeId="test-store-123",
            PhoneNumber="5551234567",
            transactionId="txn-456",
            OrderNumber="ORD-789",
            OrderDate="03/19/2026 12:30:00 PM",
            trackingLink=None,
            brandId=None,
        )

        with pytest.raises(ValueError, match="Event must not be None"):
            await update_order_status(mock_session, webhook_request)


def test_generate_notification_text_uses_db_id_when_order_id_missing() -> None:
    """Notification text should still identify orders without external IDs."""
    order = _order_result(order_id=None, status="paid")

    assert _generate_notification_text(order) == f"Order #{order.id} status: paid"


@pytest.mark.asyncio
async def test_send_order_notification_rejects_missing_store_phone() -> None:
    """Notification send should fail before relay when store phone is absent."""
    order = _order_result(store_phone_number=None)

    with pytest.raises(ValueError, match="Invalid store phone number"):
        await send_order_notification(order)


@pytest.mark.asyncio
async def test_send_order_notification_rejects_missing_user_phone() -> None:
    """Notification send should fail before relay when user phone is absent."""
    order = _order_result(user_phone_number="")

    with pytest.raises(ValueError, match="Invalid user phone number"):
        await send_order_notification(order)
