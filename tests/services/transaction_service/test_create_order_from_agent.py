"""Tests for create_order_from_agent_async function."""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from db.tables.types import IntegrationProvider
from services.transaction_service._implementation import create_order_from_agent_async


class FakeOrderDetails:
    """Fake order details object similar to pal-agents output."""

    def __init__(
        self,
        vendor: str = "adora",
        order_id: str | None = "ORDER-123",
        store_id: str = "STORE-456",
        user_phone_number: str = "+15551234567",
        tracking_link: str = "https://example.com/track",
        status: str = "pending",
        fulfillment_strategy: str = "pickup",
        subtotal: float | None = 45.99,
        order_time: str | datetime | None = "2026-03-14T12:30:00",
        order_items: list | None = None,
        display_payload: dict[str, object] | None = None,
    ):
        self.vendor = vendor
        self.order_id = order_id
        self.store_id = store_id
        self.user_phone_number = user_phone_number
        self.tracking_link = tracking_link
        self.status = status
        self.fulfillment_strategy = fulfillment_strategy
        self.subtotal = subtotal
        self.order_time = order_time
        self.order_items = order_items or [
            {"item_id": "1", "item_name": "Burger", "quantity": 2}
        ]
        self.display_payload = display_payload


@pytest.fixture
def mock_session():
    """Mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_order():
    """Mock order object."""
    order = Mock()
    order.id = uuid.uuid4()
    order.order_id = "ORDER-123"
    order.store_id = "STORE-456"
    order.vendor = IntegrationProvider.adora
    order.conversation_id = uuid.uuid4()
    order.subtotal = Decimal("45.99")
    return order


@pytest.fixture
def conversation_id():
    """Sample conversation ID."""
    return uuid.uuid4()


@pytest.mark.asyncio
class TestCreateOrderFromAgentAsync:
    """Tests for create_order_from_agent_async."""

    async def test_create_order_success(
        self, mock_session, mock_order, conversation_id
    ):
        """Test successful order creation from agent."""
        order_details = FakeOrderDetails()

        # Mock run_sync to execute the inner function
        async def mock_run_sync(func):
            mock_sync_session = Mock()
            mock_repo = Mock()
            mock_repo.create_order = Mock(return_value=mock_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        # Execute
        result = await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert result is not None
        assert result.id == mock_order.id
        assert mock_session.commit.called
        mock_session.refresh.assert_awaited_once_with(mock_order)
        assert not mock_session.rollback.called

    async def test_invalid_vendor_returns_none(self, mock_session, conversation_id):
        """Test that invalid vendor returns None."""
        order_details = FakeOrderDetails(vendor="invalid_vendor_name")

        # Execute
        result = await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert result is None
        assert not mock_session.commit.called

    async def test_type_conversion_vendor_to_enum(
        self, mock_session, mock_order, conversation_id
    ):
        """Test vendor string is converted to IntegrationProvider enum."""
        order_details = FakeOrderDetails(vendor="adora")

        captured_vendor = None

        async def mock_run_sync(func):
            nonlocal captured_vendor
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create_order(**kwargs):
                nonlocal captured_vendor
                captured_vendor = kwargs.get("vendor")
                return mock_order

            mock_repo.create_order = Mock(side_effect=capture_create_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        # Execute
        await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert captured_vendor == IntegrationProvider.adora

    async def test_type_conversion_subtotal_to_decimal(
        self, mock_session, mock_order, conversation_id
    ):
        """Test subtotal float is converted to Decimal."""
        order_details = FakeOrderDetails(subtotal=45.99)

        captured_subtotal = None

        async def mock_run_sync(func):
            nonlocal captured_subtotal
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create_order(**kwargs):
                nonlocal captured_subtotal
                captured_subtotal = kwargs.get("subtotal")
                return mock_order

            mock_repo.create_order = Mock(side_effect=capture_create_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        # Execute
        await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert isinstance(captured_subtotal, Decimal)
        assert captured_subtotal == Decimal("45.99")

    async def test_type_conversion_order_time_to_datetime(
        self, mock_session, mock_order, conversation_id
    ):
        """Test order_time string is converted to datetime."""
        order_details = FakeOrderDetails(order_time="2026-03-14T12:30:00")

        captured_order_time = None

        async def mock_run_sync(func):
            nonlocal captured_order_time
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create_order(**kwargs):
                nonlocal captured_order_time
                captured_order_time = kwargs.get("order_time")
                return mock_order

            mock_repo.create_order = Mock(side_effect=capture_create_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        # Execute
        await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert isinstance(captured_order_time, datetime)
        assert captured_order_time == datetime(2026, 3, 14, 12, 30, 0)

    async def test_handles_none_subtotal(
        self, mock_session, mock_order, conversation_id
    ):
        """Test that None subtotal is handled correctly."""
        order_details = FakeOrderDetails(subtotal=None)

        captured_subtotal = "NOT_SET"

        async def mock_run_sync(func):
            nonlocal captured_subtotal
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create_order(**kwargs):
                nonlocal captured_subtotal
                captured_subtotal = kwargs.get("subtotal")
                return mock_order

            mock_repo.create_order = Mock(side_effect=capture_create_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        # Execute
        result = await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert result is not None
        assert captured_subtotal is None

    async def test_handles_datetime_object_order_time(
        self, mock_session, mock_order, conversation_id
    ):
        """Test that datetime object order_time is passed through."""
        order_time = datetime(2026, 3, 14, 12, 30, 0)
        order_details = FakeOrderDetails(order_time=order_time)

        captured_order_time = None

        async def mock_run_sync(func):
            nonlocal captured_order_time
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create_order(**kwargs):
                nonlocal captured_order_time
                captured_order_time = kwargs.get("order_time")
                return mock_order

            mock_repo.create_order = Mock(side_effect=capture_create_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        # Execute
        await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert captured_order_time == order_time

    async def test_passes_display_payload_to_repository(
        self, mock_session, mock_order, conversation_id
    ):
        """Test display payload is passed through to order persistence."""
        display_payload = {
            "summary": "Burger x2",
            "items": [{"name": "Burger", "quantity": 2}],
        }
        order_details = FakeOrderDetails(display_payload=display_payload)

        captured_display_payload = None

        async def mock_run_sync(func):
            nonlocal captured_display_payload
            mock_sync_session = Mock()
            mock_repo = Mock()

            def capture_create_order(**kwargs):
                nonlocal captured_display_payload
                captured_display_payload = kwargs.get("display_payload")
                return mock_order

            mock_repo.create_order = Mock(side_effect=capture_create_order)

            with patch(
                "services.transaction_service._implementation.OrderRepository",
                return_value=mock_repo,
            ):
                return func(mock_sync_session)

        mock_session.run_sync = mock_run_sync

        await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        assert captured_display_payload == display_payload

    async def test_error_handling_rollback(self, mock_session, conversation_id):
        """Test that errors trigger rollback and return None."""
        order_details = FakeOrderDetails()

        # Mock run_sync to raise an exception
        async def mock_run_sync(func):
            raise Exception("Database error")

        mock_session.run_sync = mock_run_sync

        # Execute
        result = await create_order_from_agent_async(
            session=mock_session,
            order_details=order_details,
            conversation_id=conversation_id,
        )

        # Assert
        assert result is None
        assert mock_session.rollback.called
        assert not mock_session.commit.called
