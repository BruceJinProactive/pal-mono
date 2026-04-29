"""Tests for the activate subscription admin endpoint implementation."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes.admin._subscription import activate_subscription
from api.schemas.admin.subscription import (
    ActivateSubscriptionRequest,
    ActivateSubscriptionResponse,
)
from db.tables.types import PaymentMethod, SubscriptionStatus


class TestActivateSubscription:
    """Tests for activate_subscription implementation function."""

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        ctx = MagicMock()
        ctx.username = "admin-user"
        ctx.email = "admin@example.com"
        return ctx

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_account(self) -> MagicMock:
        account = MagicMock()
        account.id = uuid.uuid4()
        account.name = "test-account"
        return account

    @pytest.fixture
    def mock_activated_subscription(self) -> MagicMock:
        sub = MagicMock()
        sub.external_id = uuid.uuid4()
        sub.status = SubscriptionStatus.active
        sub.stripe_subscription_id = "sub_test123"
        sub.payment_method = PaymentMethod.invoice
        return sub

    @pytest.fixture
    def default_request(self) -> ActivateSubscriptionRequest:
        return ActivateSubscriptionRequest()

    @pytest.fixture
    def credit_request(self) -> ActivateSubscriptionRequest:
        return ActivateSubscriptionRequest(
            grant_credit_amount_cents=50000, currency="usd"
        )

    @patch("api.routes.admin._subscription.subscription_service")
    @patch("api.routes.admin._subscription.account_service")
    def test_activates_subscription_successfully(
        self,
        mock_account_svc: MagicMock,
        mock_sub_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        mock_account: MagicMock,
        mock_activated_subscription: MagicMock,
        default_request: ActivateSubscriptionRequest,
    ) -> None:
        mock_account_svc.get_account.return_value = mock_account
        mock_sub_svc.activate_subscription_without_payment_method.return_value = (
            mock_activated_subscription
        )
        external_id = uuid.uuid4()

        result = activate_subscription(
            mock_context, mock_session, "test-account", external_id, default_request
        )

        assert isinstance(result, ActivateSubscriptionResponse)
        assert result.external_id == mock_activated_subscription.external_id
        assert result.status == "active"
        assert result.stripe_subscription_id == "sub_test123"
        assert result.collection_method == "send_invoice"
        assert result.message == "Subscription activated successfully"

        mock_sub_svc.activate_subscription_without_payment_method.assert_called_once_with(
            session=mock_session,
            context=mock_context,
            account_id=mock_account.id,
            external_id=external_id,
            grant_credit_amount_cents=None,
            currency="usd",
        )

    @patch("api.routes.admin._subscription.subscription_service")
    @patch("api.routes.admin._subscription.account_service")
    def test_passes_credit_grant_params(
        self,
        mock_account_svc: MagicMock,
        mock_sub_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        mock_account: MagicMock,
        mock_activated_subscription: MagicMock,
        credit_request: ActivateSubscriptionRequest,
    ) -> None:
        mock_account_svc.get_account.return_value = mock_account
        mock_sub_svc.activate_subscription_without_payment_method.return_value = (
            mock_activated_subscription
        )

        activate_subscription(
            mock_context, mock_session, "test-account", uuid.uuid4(), credit_request
        )

        call_kwargs = (
            mock_sub_svc.activate_subscription_without_payment_method.call_args.kwargs
        )
        assert call_kwargs["grant_credit_amount_cents"] == 50000
        assert call_kwargs["currency"] == "usd"

    @patch("api.routes.admin._subscription.account_service")
    def test_raises_404_when_account_not_found(
        self,
        mock_account_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        default_request: ActivateSubscriptionRequest,
    ) -> None:
        mock_account_svc.get_account.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            activate_subscription(
                mock_context,
                mock_session,
                "missing-account",
                uuid.uuid4(),
                default_request,
            )

        assert exc_info.value.status_code == 404

    @patch("api.routes.admin._subscription.subscription_service")
    @patch("api.routes.admin._subscription.account_service")
    def test_raises_404_when_subscription_not_found(
        self,
        mock_account_svc: MagicMock,
        mock_sub_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        mock_account: MagicMock,
        default_request: ActivateSubscriptionRequest,
    ) -> None:
        mock_account_svc.get_account.return_value = mock_account
        mock_sub_svc.activate_subscription_without_payment_method.side_effect = (
            ValueError("Subscription does not exist")
        )

        with pytest.raises(HTTPException) as exc_info:
            activate_subscription(
                mock_context,
                mock_session,
                "test-account",
                uuid.uuid4(),
                default_request,
            )

        assert exc_info.value.status_code == 404

    @patch("api.routes.admin._subscription.subscription_service")
    @patch("api.routes.admin._subscription.account_service")
    def test_raises_400_for_invalid_state(
        self,
        mock_account_svc: MagicMock,
        mock_sub_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        mock_account: MagicMock,
        default_request: ActivateSubscriptionRequest,
    ) -> None:
        mock_account_svc.get_account.return_value = mock_account
        mock_sub_svc.activate_subscription_without_payment_method.side_effect = (
            ValueError("Subscription is already active")
        )

        with pytest.raises(HTTPException) as exc_info:
            activate_subscription(
                mock_context,
                mock_session,
                "test-account",
                uuid.uuid4(),
                default_request,
            )

        assert exc_info.value.status_code == 400

    @patch("api.routes.admin._subscription.subscription_service")
    @patch("api.routes.admin._subscription.account_service")
    def test_raises_500_for_unexpected_error(
        self,
        mock_account_svc: MagicMock,
        mock_sub_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        mock_account: MagicMock,
        default_request: ActivateSubscriptionRequest,
    ) -> None:
        mock_account_svc.get_account.return_value = mock_account
        mock_sub_svc.activate_subscription_without_payment_method.side_effect = (
            RuntimeError("Stripe timeout")
        )

        with pytest.raises(HTTPException) as exc_info:
            activate_subscription(
                mock_context,
                mock_session,
                "test-account",
                uuid.uuid4(),
                default_request,
            )

        assert exc_info.value.status_code == 500

    @patch("api.routes.admin._subscription.subscription_service")
    @patch("api.routes.admin._subscription.account_service")
    def test_trialing_status_returned_for_future_start(
        self,
        mock_account_svc: MagicMock,
        mock_sub_svc: MagicMock,
        mock_context: MagicMock,
        mock_session: MagicMock,
        mock_account: MagicMock,
        default_request: ActivateSubscriptionRequest,
    ) -> None:
        trialing_sub = MagicMock()
        trialing_sub.external_id = uuid.uuid4()
        trialing_sub.status = SubscriptionStatus.trialing
        trialing_sub.stripe_subscription_id = "sub_trial456"
        trialing_sub.payment_method = PaymentMethod.invoice

        mock_account_svc.get_account.return_value = mock_account
        mock_sub_svc.activate_subscription_without_payment_method.return_value = (
            trialing_sub
        )

        result = activate_subscription(
            mock_context, mock_session, "test-account", uuid.uuid4(), default_request
        )

        assert result.status == "trialing"
        assert result.stripe_subscription_id == "sub_trial456"


class TestActivateSubscriptionRequestValidation:
    """Tests for ActivateSubscriptionRequest schema validation."""

    def test_currency_normalizes_to_lowercase(self) -> None:
        req = ActivateSubscriptionRequest(currency="USD")
        assert req.currency == "usd"

    def test_currency_strips_whitespace(self) -> None:
        req = ActivateSubscriptionRequest(currency=" eur ")
        assert req.currency == "eur"

    def test_currency_rejects_non_alpha(self) -> None:
        with pytest.raises(ValidationError, match="3-letter ISO 4217"):
            ActivateSubscriptionRequest(currency="u$d")

    def test_currency_rejects_wrong_length(self) -> None:
        with pytest.raises(ValidationError, match="3-letter ISO 4217"):
            ActivateSubscriptionRequest(currency="us")

    def test_currency_rejects_too_long(self) -> None:
        with pytest.raises(ValidationError, match="3-letter ISO 4217"):
            ActivateSubscriptionRequest(currency="usdd")

    def test_negative_credit_amount_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-negative"):
            ActivateSubscriptionRequest(grant_credit_amount_cents=-100)
