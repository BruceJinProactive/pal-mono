"""Tests for the invoice.created webhook handler (accrued balance logic)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from api.routes.integrations.stripe._implementation import _handle_invoice_created


class _FakeInvoiceList:
    """Mimics stripe.Invoice.list() result with auto_paging_iter."""

    def __init__(self, invoices: list[dict]) -> None:
        self._invoices = invoices

    def auto_paging_iter(self):  # type: ignore[no-untyped-def]
        yield from self._invoices


@pytest.fixture
def async_session() -> AsyncMock:
    return AsyncMock()


class TestHandleInvoiceCreated:
    """Tests for _handle_invoice_created webhook handler."""

    @pytest.mark.asyncio
    async def test_skips_non_subscription_invoice(
        self, async_session: AsyncMock
    ) -> None:
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": None,
            }
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            await _handle_invoice_created(event_data, async_session)
            mock_stripe.Invoice.list.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_missing_customer(self, async_session: AsyncMock) -> None:
        event_data = {
            "object": {
                "id": "in_new",
                "customer": None,
                "subscription": "sub_123",
            }
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            await _handle_invoice_created(event_data, async_session)
            mock_stripe.Invoice.list.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_accrual_when_no_open_invoices(
        self, async_session: AsyncMock
    ) -> None:
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([])
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

            mock_stripe.Invoice.list.assert_called_once_with(
                customer="cus_123",
                subscription="sub_456",
                status="open",
            )
            mock_stripe.InvoiceItem.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_accrual_when_invoices_not_past_due(
        self, async_session: AsyncMock
    ) -> None:
        """Open invoices that are not yet past due should not be accrued."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        # due_date far in the future
        future_invoice = {
            "id": "in_old",
            "due_date": 9999999999,
            "amount_remaining": 5000,
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([future_invoice])
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

            mock_stripe.InvoiceItem.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_current_invoice_in_open_list(
        self, async_session: AsyncMock
    ) -> None:
        """The new invoice itself should not be counted as past-due."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        same_invoice = {
            "id": "in_new",
            "due_date": 1000000000,
            "amount_remaining": 5000,
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([same_invoice])
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

            mock_stripe.InvoiceItem.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_accrues_past_due_invoices_and_voids(
        self, async_session: AsyncMock
    ) -> None:
        """Past-due open invoices should be accrued and voided."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        past_due_1 = {
            "id": "in_old_1",
            "due_date": 1000000000,  # well in the past
            "amount_remaining": 3000,
        }
        past_due_2 = {
            "id": "in_old_2",
            "due_date": 1000000001,
            "amount_remaining": 2000,
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList(
                [past_due_1, past_due_2]
            )
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

            # Should add a single line item with total accrued amount + idempotency key
            mock_stripe.InvoiceItem.create.assert_called_once_with(
                customer="cus_123",
                invoice="in_new",
                amount=5000,
                currency="usd",
                description="Prior unpaid balance (2 invoice(s))",
                stripe_account=None,
                idempotency_key="accrual-in_new-in_old_1-in_old_2",
            )

            # Should retrieve and void both old invoices
            assert mock_stripe.Invoice.retrieve.call_count == 2
            mock_stripe.Invoice.retrieve.assert_any_call("in_old_1")
            mock_stripe.Invoice.retrieve.assert_any_call("in_old_2")
            assert (
                mock_stripe.Invoice.retrieve.return_value.void_invoice.call_count == 2
            )

    @pytest.mark.asyncio
    async def test_skips_zero_remaining_invoices(
        self, async_session: AsyncMock
    ) -> None:
        """Open invoices with zero remaining should not be accrued."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        zero_remaining = {
            "id": "in_old",
            "due_date": 1000000000,
            "amount_remaining": 0,
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([zero_remaining])
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

            mock_stripe.InvoiceItem.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_stripe_list_error_gracefully(
        self, async_session: AsyncMock
    ) -> None:
        """If listing open invoices fails, handler should log and return."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
            }
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.StripeError = stripe.StripeError
            mock_stripe.Invoice.list.side_effect = stripe.StripeError("API error")

            await _handle_invoice_created(event_data, async_session)

            mock_stripe.InvoiceItem.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_invoice_item_create_error_gracefully(
        self, async_session: AsyncMock
    ) -> None:
        """If adding the line item fails, old invoices should NOT be voided."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        past_due = {
            "id": "in_old",
            "due_date": 1000000000,
            "amount_remaining": 5000,
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([past_due])
            mock_stripe.StripeError = stripe.StripeError
            mock_stripe.InvoiceItem.create.side_effect = stripe.StripeError(
                "Failed to create item"
            )

            await _handle_invoice_created(event_data, async_session)

            # Should NOT void invoices if line item creation failed
            mock_stripe.Invoice.retrieve.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_voiding_on_partial_void_failure(
        self, async_session: AsyncMock
    ) -> None:
        """If voiding one invoice fails, should continue voiding the rest."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        past_due_1 = {
            "id": "in_old_1",
            "due_date": 1000000000,
            "amount_remaining": 3000,
        }
        past_due_2 = {
            "id": "in_old_2",
            "due_date": 1000000001,
            "amount_remaining": 2000,
        }

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList(
                [past_due_1, past_due_2]
            )
            mock_stripe.StripeError = stripe.StripeError
            mock_retrieved = MagicMock()
            # First void fails, second succeeds
            mock_retrieved.void_invoice.side_effect = [
                stripe.StripeError("Cannot void"),
                MagicMock(),
            ]
            mock_stripe.Invoice.retrieve.return_value = mock_retrieved

            await _handle_invoice_created(event_data, async_session)

            # Both should be attempted
            assert mock_stripe.Invoice.retrieve.call_count == 2
            assert mock_retrieved.void_invoice.call_count == 2
