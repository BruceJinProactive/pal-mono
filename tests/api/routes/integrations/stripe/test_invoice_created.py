"""Tests for the invoice.created webhook handler (accrued balance & draft finalization)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from api.routes.integrations.stripe._implementation import (
    _finalize_previous_draft_invoice,
    _handle_invoice_created,
    _handle_subscription_deleted,
)


class _FakeInvoiceList:
    """Mimics stripe.Invoice.list() result with auto_paging_iter."""

    def __init__(self, invoices: list[dict]) -> None:
        self._invoices = invoices

    def auto_paging_iter(self):  # type: ignore[no-untyped-def]
        yield from self._invoices


@pytest.fixture
def async_session() -> AsyncMock:
    return AsyncMock()


PATCH_FINALIZE = (
    "api.routes.integrations.stripe._implementation._finalize_previous_draft_invoice"
)
PATCH_AUTOMATED_EMAIL = (
    "api.routes.integrations.stripe._implementation.send_automated_invoice_email"
)


class TestHandleInvoiceCreated:
    """Tests for _handle_invoice_created webhook handler (accrual logic)."""

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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock) as mock_finalize,
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([])
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

            # Verify arrears billing: finalize previous draft + set auto_advance
            mock_stripe.Invoice.modify.assert_called_once_with(
                "in_new", auto_advance=False
            )
            mock_finalize.assert_awaited_once_with(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )
            mock_stripe.Invoice.list.assert_called_once_with(
                customer="cus_123",
                subscription="sub_456",
                status="open",
            )
            mock_stripe.InvoiceItem.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_accrual_when_invoice_has_no_due_date(
        self, async_session: AsyncMock
    ) -> None:
        """Newly finalized invoices with no due_date should not be accrued."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        # Invoice with no due_date (e.g. just finalized from draft)
        no_due_date_invoice = {
            "id": "in_old",
            "due_date": None,
            "amount_remaining": 5000,
        }

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList(
                [no_due_date_invoice]
            )
            mock_stripe.StripeError = stripe.StripeError

            await _handle_invoice_created(event_data, async_session)

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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock),
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
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


class TestFinalizePreviousDraftInvoice:
    """Tests for _finalize_previous_draft_invoice."""

    @pytest.mark.asyncio
    async def test_finalizes_previous_draft_invoice(self) -> None:
        """Should finalize, send, and email for draft invoices not the current one."""
        previous_draft = MagicMock()
        previous_draft.id = "in_prev_draft"
        current_draft = MagicMock()
        current_draft.id = "in_new"

        with (
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
            patch(PATCH_AUTOMATED_EMAIL) as mock_email,
        ):
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList(
                [previous_draft, current_draft]
            )
            mock_stripe.StripeError = stripe.StripeError

            await _finalize_previous_draft_invoice(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )

            mock_stripe.Invoice.list.assert_called_once_with(
                customer="cus_123",
                subscription="sub_456",
                status="draft",
            )
            mock_stripe.Invoice.finalize_invoice.assert_called_once_with(
                "in_prev_draft"
            )
            mock_email.assert_called_once_with(
                finalized_invoice_id="in_prev_draft",
                stripe_customer_id="cus_123",
            )

    @pytest.mark.asyncio
    async def test_skips_current_invoice(self) -> None:
        """Should not finalize the newly created invoice."""
        current_draft = MagicMock()
        current_draft.id = "in_new"

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([current_draft])
            mock_stripe.StripeError = stripe.StripeError

            await _finalize_previous_draft_invoice(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )

            mock_stripe.Invoice.finalize_invoice.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_drafts_found(self) -> None:
        """Should handle gracefully when no drafts exist."""
        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([])
            mock_stripe.StripeError = stripe.StripeError

            await _finalize_previous_draft_invoice(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )

            mock_stripe.Invoice.finalize_invoice.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_list_error_gracefully(self) -> None:
        """Should not raise if listing drafts fails."""
        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.StripeError = stripe.StripeError
            mock_stripe.Invoice.list.side_effect = stripe.StripeError("API error")

            await _finalize_previous_draft_invoice(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )

            mock_stripe.Invoice.finalize_invoice.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_finalize_error_gracefully(self) -> None:
        """Should log and continue if finalizing a draft fails."""
        previous_draft = MagicMock()
        previous_draft.id = "in_prev_draft"

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([previous_draft])
            mock_stripe.StripeError = stripe.StripeError
            mock_stripe.Invoice.finalize_invoice.side_effect = stripe.StripeError(
                "Cannot finalize"
            )

            # Should not raise
            await _finalize_previous_draft_invoice(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )

    @pytest.mark.asyncio
    async def test_skips_draft_with_no_id(self) -> None:
        """Should skip drafts that have no id attribute."""
        draft_no_id = MagicMock()
        draft_no_id.id = None

        with patch(
            "api.routes.integrations.stripe._implementation.stripe"
        ) as mock_stripe:
            mock_stripe.Invoice.list.return_value = _FakeInvoiceList([draft_no_id])
            mock_stripe.StripeError = stripe.StripeError

            await _finalize_previous_draft_invoice(
                invoice_id="in_new",
                stripe_customer_id="cus_123",
                subscription_id="sub_456",
            )

            mock_stripe.Invoice.finalize_invoice.assert_not_called()


class TestInvoiceCreatedAutoAdvanceError:
    """Tests for auto_advance error handling in _handle_invoice_created."""

    @pytest.mark.asyncio
    async def test_raises_when_invoice_modify_fails(
        self, async_session: AsyncMock
    ) -> None:
        """Handler should re-raise so Stripe retries the webhook."""
        event_data = {
            "object": {
                "id": "in_new",
                "customer": "cus_123",
                "subscription": "sub_456",
                "currency": "usd",
            }
        }

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock) as mock_finalize,
            patch(
                "api.routes.integrations.stripe._implementation.stripe"
            ) as mock_stripe,
        ):
            mock_stripe.StripeError = stripe.StripeError
            mock_stripe.Invoice.modify.side_effect = stripe.StripeError(
                "Invoice not found"
            )

            with pytest.raises(stripe.StripeError, match="Invoice not found"):
                await _handle_invoice_created(event_data, async_session)

            # Should NOT proceed to finalize since modify failed
            mock_finalize.assert_not_awaited()


class TestSubscriptionDeletedFinalization:
    """Tests for draft invoice finalization on subscription deletion."""

    @pytest.mark.asyncio
    async def test_finalizes_drafts_on_deletion(self, async_session: AsyncMock) -> None:
        """Should finalize draft invoices when subscription is deleted."""
        event_data = {
            "object": {
                "id": "sub_123",
                "customer": "cus_456",
                "canceled_at": 1700000000,
            }
        }

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock) as mock_finalize,
            patch(
                "api.routes.integrations.stripe._implementation.subscription_service"
            ) as mock_sub_service,
        ):
            mock_sub_service.handle_subscription_deleted = AsyncMock(return_value=True)

            await _handle_subscription_deleted(event_data, async_session)

            mock_finalize.assert_awaited_once_with(
                invoice_id="",
                stripe_customer_id="cus_456",
                subscription_id="sub_123",
            )
            mock_sub_service.handle_subscription_deleted.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_finalization_without_customer_id(
        self, async_session: AsyncMock
    ) -> None:
        """Should not finalize if customer ID is missing."""
        event_data = {
            "object": {
                "id": "sub_123",
                "customer": None,
                "canceled_at": 1700000000,
            }
        }

        with (
            patch(PATCH_FINALIZE, new_callable=AsyncMock) as mock_finalize,
            patch(
                "api.routes.integrations.stripe._implementation.subscription_service"
            ) as mock_sub_service,
        ):
            mock_sub_service.handle_subscription_deleted = AsyncMock(return_value=True)

            await _handle_subscription_deleted(event_data, async_session)

            mock_finalize.assert_not_awaited()
