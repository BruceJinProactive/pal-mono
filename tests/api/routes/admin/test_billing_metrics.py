"""Tests for billing metrics endpoint."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin._billing import get_billing_metrics


def _make_context() -> MagicMock:
    context = MagicMock()
    context.email = "admin@test.com"
    context.username = str(uuid.uuid4())
    return context


def _make_account() -> MagicMock:
    account = MagicMock()
    account.id = uuid.uuid4()
    account.name = "bobs-pizza"
    return account


class TestGetBillingMetrics:
    """Tests for get_billing_metrics endpoint."""

    def test_returns_metrics_for_valid_account(self) -> None:
        """Should return billing metrics when account exists and has data."""
        account = _make_account()
        session = MagicMock()
        context = _make_context()

        # call_data tuple: (total_calls, avg_duration, avg_turn_latency, short, long, transfer, rate, pos, neutral, neg)
        mock_call_data = [(342, 47.3, 1.2, 10, 5, 3, 0.01, 200, 100, 42)]
        # conversion_data tuple: (total_convs, convs_with_orders, paid_orders, total_subtotal, paid_total, total_reservations, total_waitlists)
        mock_conversion_data = [(500, 200, 156, 5000.0, 4832.50, 28, 5)]

        with (
            patch(
                "api.routes.admin._billing.AccountRepository"
            ) as mock_account_repo_cls,
            patch(
                "api.routes.admin._billing.AnalyticsRepository"
            ) as mock_analytics_repo_cls,
        ):
            mock_account_repo_cls.return_value.get_account.return_value = account
            mock_analytics_repo = mock_analytics_repo_cls.return_value
            mock_analytics_repo.get_calls_time_summary.return_value = mock_call_data
            mock_analytics_repo.get_conversion_summary.return_value = (
                mock_conversion_data
            )

            result = get_billing_metrics(
                "bobs-pizza", "2026-04-01", "2026-04-30", context, session
            )

        assert result.account_name == "bobs-pizza"
        assert result.period_start == "2026-04-01"
        assert result.period_end == "2026-04-30"
        assert result.total_calls == 342
        assert result.avg_call_duration_seconds == 47.3
        assert result.total_reservations == 28
        assert result.total_orders == 156
        assert result.order_total_dollars == 4832.50
        assert result.template_variant == "ordering_reservation"
        assert result.template_id == 44949424

    def test_returns_zeros_when_no_data(self) -> None:
        """Should return zeros when there is no analytics data."""
        account = _make_account()
        session = MagicMock()
        context = _make_context()

        with (
            patch(
                "api.routes.admin._billing.AccountRepository"
            ) as mock_account_repo_cls,
            patch(
                "api.routes.admin._billing.AnalyticsRepository"
            ) as mock_analytics_repo_cls,
        ):
            mock_account_repo_cls.return_value.get_account.return_value = account
            mock_analytics_repo = mock_analytics_repo_cls.return_value
            mock_analytics_repo.get_calls_time_summary.return_value = []
            mock_analytics_repo.get_conversion_summary.return_value = []

            result = get_billing_metrics(
                "bobs-pizza", "2026-04-01", "2026-04-30", context, session
            )

        assert result.total_calls == 0
        assert result.avg_call_duration_seconds == 0.0
        assert result.total_reservations == 0
        assert result.total_orders == 0
        assert result.order_total_dollars == 0.0
        assert result.template_variant == "answering"
        assert result.template_id == 42569088

    def test_raises_404_when_account_not_found(self) -> None:
        """Should raise 404 when account doesn't exist."""
        session = MagicMock()
        context = _make_context()

        with patch(
            "api.routes.admin._billing.AccountRepository"
        ) as mock_account_repo_cls:
            mock_account_repo_cls.return_value.get_account.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                get_billing_metrics(
                    "nonexistent", "2026-04-01", "2026-04-30", context, session
                )

            assert exc_info.value.status_code == 404

    def test_raises_400_for_invalid_date(self) -> None:
        """Should raise 400 for invalid date format."""
        session = MagicMock()
        context = _make_context()

        with pytest.raises(HTTPException) as exc_info:
            get_billing_metrics(
                "bobs-pizza", "not-a-date", "2026-04-30", context, session
            )

        assert exc_info.value.status_code == 400

    def test_raises_400_for_reversed_date_range(self) -> None:
        """Should raise 400 when start_date is after end_date."""
        session = MagicMock()
        context = _make_context()

        with pytest.raises(HTTPException) as exc_info:
            get_billing_metrics(
                "bobs-pizza", "2026-04-30", "2026-04-01", context, session
            )

        assert exc_info.value.status_code == 400
        assert "start_date must be before end_date" in exc_info.value.detail
