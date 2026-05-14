"""Tests for send_automated_invoice_email and _select_template_id."""

import uuid
from unittest.mock import MagicMock, patch

from services.subscription_service.invoice_email_service import (
    TEMPLATE_ID_ANSWERING,
    TEMPLATE_ID_ORDERING,
    TEMPLATE_ID_ORDERING_RESERVATION,
    TEMPLATE_ID_RESERVATION,
    _select_template_id,
    send_automated_invoice_email,
)

MODULE = "services.subscription_service.invoice_email_service"


class TestSelectTemplateId:
    """Tests for template selection logic."""

    def test_returns_ordering_reservation_when_both(self) -> None:
        assert _select_template_id(10, 5) == TEMPLATE_ID_ORDERING_RESERVATION

    def test_returns_ordering_when_only_orders(self) -> None:
        assert _select_template_id(10, 0) == TEMPLATE_ID_ORDERING

    def test_returns_reservation_when_only_reservations(self) -> None:
        assert _select_template_id(0, 5) == TEMPLATE_ID_RESERVATION

    def test_returns_answering_when_neither(self) -> None:
        assert _select_template_id(0, 0) == TEMPLATE_ID_ANSWERING


class TestSendAutomatedInvoiceEmail:
    """Tests for the automated invoice email flow."""

    def _mock_invoice(
        self, period_start: int = 1711929600, period_end: int = 1714521600
    ) -> MagicMock:
        """Create a mock Stripe invoice with period timestamps."""
        inv = MagicMock()
        inv.period_start = period_start
        inv.period_end = period_end
        return inv

    def _mock_account(
        self,
        notification_email: str | None = "billing@example.com",
        display_name: str | None = "Test Restaurant",
        name: str = "test-restaurant",
    ) -> MagicMock:
        account = MagicMock()
        account.notification_email = notification_email
        account.display_name = display_name
        account.name = name
        account.id = uuid.uuid4()
        return account

    @patch(f"{MODULE}.send_invoice_email_with_analytics")
    @patch(f"{MODULE}.stripe_invoice")
    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_happy_path_sends_email(
        self,
        mock_stripe: MagicMock,
        mock_session_local: MagicMock,
        mock_stripe_invoice: MagicMock,
        mock_send_email: MagicMock,
    ) -> None:
        """Full happy path: retrieves invoice, queries analytics, sends email."""
        # Stripe invoice with April 2026 billing period
        mock_stripe.Invoice.retrieve.return_value = self._mock_invoice(
            period_start=1711929600,  # 2024-04-01
            period_end=1714521600,  # 2024-04-30
        )

        # Account lookup
        account = self._mock_account()
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)
        mock_account_repo = MagicMock()
        mock_account_repo.get_account_by_stripe_customer_id.return_value = account
        mock_analytics_repo = MagicMock()
        # call_data: (total_calls, avg_duration, ...)
        mock_analytics_repo.get_calls_time_summary.return_value = [(150, 180.0)]
        # conversion_data: (total_convs, convs_with_orders, paid_orders, subtotal, paid_total, reservations, waitlists)
        mock_analytics_repo.get_conversion_summary.return_value = [
            (100, 50, 42, 5000.0, 4200.0, 15, 3)
        ]

        # Patch repo constructors
        with (
            patch(f"{MODULE}.AccountRepository", return_value=mock_account_repo),
            patch(f"{MODULE}.AnalyticsRepository", return_value=mock_analytics_repo),
        ):
            mock_stripe_invoice.get_invoice_pdf.return_value = b"fake-pdf-bytes"

            send_automated_invoice_email(
                finalized_invoice_id="in_finalized_123",
                stripe_customer_id="cus_456",
            )

        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args[1]
        assert call_kwargs["to_email"] == "billing@example.com"
        assert call_kwargs["display_name"] == "Test Restaurant"
        assert call_kwargs["total_orders"] == 42
        assert call_kwargs["total_reservations"] == 15
        assert call_kwargs["template_id"] == TEMPLATE_ID_ORDERING_RESERVATION
        assert call_kwargs["pdf_content"] == b"fake-pdf-bytes"
        assert "billing_period" in call_kwargs
        assert call_kwargs["billing_period"] != ""

    @patch(f"{MODULE}.stripe")
    def test_skips_when_invoice_missing_period(self, mock_stripe: MagicMock) -> None:
        """Should return early if invoice has no period dates."""
        inv = MagicMock(spec=[])  # no period_start/period_end attributes
        mock_stripe.Invoice.retrieve.return_value = inv

        # Should not raise
        send_automated_invoice_email(
            finalized_invoice_id="in_no_period",
            stripe_customer_id="cus_456",
        )

    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_skips_when_account_not_found(
        self, mock_stripe: MagicMock, mock_session_local: MagicMock
    ) -> None:
        """Should return early if no account matches the stripe customer."""
        mock_stripe.Invoice.retrieve.return_value = self._mock_invoice()

        mock_session = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)
        mock_account_repo = MagicMock()
        mock_account_repo.get_account_by_stripe_customer_id.return_value = None

        with patch(f"{MODULE}.AccountRepository", return_value=mock_account_repo):
            send_automated_invoice_email(
                finalized_invoice_id="in_123",
                stripe_customer_id="cus_unknown",
            )

    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_skips_when_no_notification_email(
        self, mock_stripe: MagicMock, mock_session_local: MagicMock
    ) -> None:
        """Should return early if account has no notification_email."""
        mock_stripe.Invoice.retrieve.return_value = self._mock_invoice()

        account = self._mock_account(notification_email=None)
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)
        mock_account_repo = MagicMock()
        mock_account_repo.get_account_by_stripe_customer_id.return_value = account

        with patch(f"{MODULE}.AccountRepository", return_value=mock_account_repo):
            send_automated_invoice_email(
                finalized_invoice_id="in_123",
                stripe_customer_id="cus_456",
            )

    @patch(f"{MODULE}.send_invoice_email_with_analytics")
    @patch(f"{MODULE}.stripe_invoice")
    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_skips_when_pdf_fetch_fails(
        self,
        mock_stripe: MagicMock,
        mock_session_local: MagicMock,
        mock_stripe_invoice: MagicMock,
        mock_send_email: MagicMock,
    ) -> None:
        """Should return early if fetching the invoice PDF fails."""
        mock_stripe.Invoice.retrieve.return_value = self._mock_invoice()

        account = self._mock_account()
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)
        mock_account_repo = MagicMock()
        mock_account_repo.get_account_by_stripe_customer_id.return_value = account
        mock_analytics_repo = MagicMock()
        mock_analytics_repo.get_calls_time_summary.return_value = [(50, 120.0)]
        mock_analytics_repo.get_conversion_summary.return_value = [
            (30, 10, 5, 500.0, 400.0, 0, 0)
        ]

        with (
            patch(f"{MODULE}.AccountRepository", return_value=mock_account_repo),
            patch(f"{MODULE}.AnalyticsRepository", return_value=mock_analytics_repo),
        ):
            mock_stripe_invoice.get_invoice_pdf.side_effect = ValueError("No PDF URL")

            send_automated_invoice_email(
                finalized_invoice_id="in_123",
                stripe_customer_id="cus_456",
            )

        mock_send_email.assert_not_called()

    @patch(f"{MODULE}.send_invoice_email_with_analytics")
    @patch(f"{MODULE}.stripe_invoice")
    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_does_not_raise_on_unexpected_error(
        self,
        mock_stripe: MagicMock,
        mock_session_local: MagicMock,
        mock_stripe_invoice: MagicMock,
        mock_send_email: MagicMock,
    ) -> None:
        """Outer try/except should catch all errors silently."""
        mock_stripe.Invoice.retrieve.side_effect = RuntimeError("Network error")

        # Should not raise
        send_automated_invoice_email(
            finalized_invoice_id="in_123",
            stripe_customer_id="cus_456",
        )

        mock_send_email.assert_not_called()

    @patch(f"{MODULE}.send_invoice_email_with_analytics")
    @patch(f"{MODULE}.stripe_invoice")
    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_excludes_eval_and_test_calls_from_analytics(
        self,
        mock_stripe: MagicMock,
        mock_session_local: MagicMock,
        mock_stripe_invoice: MagicMock,
        mock_send_email: MagicMock,
    ) -> None:
        """Should pass exclude_eval_calls and test numbers to analytics queries."""
        mock_stripe.Invoice.retrieve.return_value = self._mock_invoice()

        account = self._mock_account()
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)
        mock_account_repo = MagicMock()
        mock_account_repo.get_account_by_stripe_customer_id.return_value = account
        mock_analytics_repo = MagicMock()
        mock_analytics_repo.get_calls_time_summary.return_value = [(50, 120.0)]
        mock_analytics_repo.get_conversion_summary.return_value = [
            (30, 10, 5, 500.0, 400.0, 2, 0)
        ]

        with (
            patch(f"{MODULE}.AccountRepository", return_value=mock_account_repo),
            patch(f"{MODULE}.AnalyticsRepository", return_value=mock_analytics_repo),
            patch(
                f"{MODULE}.get_test_phone_numbers",
                return_value={"+18889738742"},
            ),
        ):
            mock_stripe_invoice.get_invoice_pdf.return_value = b"fake-pdf"

            send_automated_invoice_email(
                finalized_invoice_id="in_123",
                stripe_customer_id="cus_456",
            )

        # Verify exclusion params passed to calls query
        calls_kwargs = mock_analytics_repo.get_calls_time_summary.call_args[1]
        assert calls_kwargs["exclude_eval_calls"] is True
        assert calls_kwargs["exclude_caller_numbers"] == ["+18889738742"]

        # Verify exclusion params passed to conversion query
        conv_kwargs = mock_analytics_repo.get_conversion_summary.call_args[1]
        assert conv_kwargs["exclude_eval_calls"] is True
        assert conv_kwargs["exclude_caller_numbers"] == ["+18889738742"]

    @patch(f"{MODULE}.send_invoice_email_with_analytics")
    @patch(f"{MODULE}.stripe_invoice")
    @patch(f"{MODULE}.SyncSessionLocal")
    @patch(f"{MODULE}.stripe")
    def test_uses_account_name_when_no_display_name(
        self,
        mock_stripe: MagicMock,
        mock_session_local: MagicMock,
        mock_stripe_invoice: MagicMock,
        mock_send_email: MagicMock,
    ) -> None:
        """Should fall back to account.name if display_name is None."""
        mock_stripe.Invoice.retrieve.return_value = self._mock_invoice()

        account = self._mock_account(display_name=None, name="fallback-name")
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)
        mock_account_repo = MagicMock()
        mock_account_repo.get_account_by_stripe_customer_id.return_value = account
        mock_analytics_repo = MagicMock()
        mock_analytics_repo.get_calls_time_summary.return_value = []
        mock_analytics_repo.get_conversion_summary.return_value = []

        with (
            patch(f"{MODULE}.AccountRepository", return_value=mock_account_repo),
            patch(f"{MODULE}.AnalyticsRepository", return_value=mock_analytics_repo),
        ):
            mock_stripe_invoice.get_invoice_pdf.return_value = b"pdf"

            send_automated_invoice_email(
                finalized_invoice_id="in_123",
                stripe_customer_id="cus_456",
            )

        call_kwargs = mock_send_email.call_args[1]
        assert call_kwargs["display_name"] == "fallback-name"
        assert call_kwargs["calls_handled"] == 0
