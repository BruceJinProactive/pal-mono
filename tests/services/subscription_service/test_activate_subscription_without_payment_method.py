"""Tests for activate_subscription_without_payment_method() in _subscription.py.

Validates the admin-only flow that creates a Stripe subscription directly
(send_invoice) without requiring a payment method on the customer.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from db.tables.subscriptions import SubscriptionStatus
from db.tables.types import PaymentMethod
from services.subscription_service._subscription import (
    activate_subscription_without_payment_method,
)


@pytest.fixture
def account_id() -> uuid.UUID:
    return uuid.UUID("660e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def external_id() -> uuid.UUID:
    return uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.username = "admin-user-123"
    ctx.email = "admin@example.com"
    return ctx


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_account(account_id: uuid.UUID) -> MagicMock:
    account = MagicMock()
    account.id = account_id
    account.name = "test-account"
    account.stripe_customer_id = "cus_test123"
    account.stripe_coupon_id = None
    return account


@pytest.fixture
def mock_subscription(account_id: uuid.UUID, external_id: uuid.UUID) -> MagicMock:
    sub = MagicMock()
    sub.account_id = account_id
    sub.external_id = external_id
    sub.status = SubscriptionStatus.pending
    sub.subscription_plan = MagicMock()
    sub.subscription_plan.name = "Pro Plan"
    sub.subscription_plan.monthly_fee = 5000
    sub.subscription_plan.free_trial_days = None
    sub.start_date = datetime(
        2025, 1, 1, tzinfo=UTC
    )  # past date — immediate activation
    return sub


@pytest.fixture
def mock_project_subscriptions() -> list[MagicMock]:
    ps1 = MagicMock()
    ps1.id = uuid.uuid4()
    ps1.project_id = uuid.uuid4()
    ps1.base_price_id = "price_base_001"
    ps1.call_price_id = "price_call_001"
    ps1.order_price_id = "price_order_001"

    ps2 = MagicMock()
    ps2.id = uuid.uuid4()
    ps2.project_id = uuid.uuid4()
    ps2.base_price_id = "price_base_002"
    ps2.call_price_id = "price_call_002"
    ps2.order_price_id = None  # no order price for this project
    return [ps1, ps2]


@pytest.fixture
def mock_stripe_subscription() -> MagicMock:
    stripe_sub = MagicMock()
    stripe_sub.id = "sub_activated_123"
    return stripe_sub


# Shared patch targets
_ACCT_SUB_REPO = (
    "services.subscription_service._subscription.AccountSubscriptionRepository"
)
_PROJ_SUB_REPO = (
    "services.subscription_service._subscription.ProjectSubscriptionRepository"
)
_ACCT_SERVICE = "services.subscription_service._subscription.account_service"
_STRIPE_SUB = "services.subscription_service._subscription._stripe_subscription"
_UPDATE_ACCT_SUB = (
    "services.subscription_service._subscription.update_account_subscription"
)
_GRANT_CREDIT = "services.subscription_service._subscription.grant_credit_to_account"
_SEND_NOTIF = "services.subscription_service._subscription._send_subscription_activated_notification"


class TestActivateSubscriptionHappyPath:
    """Tests for successful activation flow."""

    @patch(_SEND_NOTIF)
    @patch(_UPDATE_ACCT_SUB)
    @patch(_STRIPE_SUB)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_activates_pending_subscription(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_update_acct_sub: MagicMock,
        mock_send_notif: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        # Setup
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )
        updated_sub = MagicMock()
        updated_sub.subscription_plan = mock_subscription.subscription_plan
        mock_update_acct_sub.return_value = updated_sub

        # Act
        result = activate_subscription_without_payment_method(
            session=mock_session,
            context=mock_context,
            account_id=account_id,
            external_id=external_id,
        )

        # Assert — Stripe subscription created with correct params
        mock_stripe_sub_module.create_subscription_direct.assert_called_once()
        create_call_kwargs = (
            mock_stripe_sub_module.create_subscription_direct.call_args[1]
        )
        assert create_call_kwargs["stripe_customer_id"] == "cus_test123"
        assert len(create_call_kwargs["line_items"]) == 5  # 3 from ps1 + 2 from ps2
        assert create_call_kwargs["metadata"] == {
            "subscription_external_id": str(external_id),
            "account_id": str(account_id),
        }
        assert create_call_kwargs["coupon_id"] is None

        # Assert — AccountSubscription updated
        mock_update_acct_sub.assert_called_once_with(
            mock_session,
            mock_context,
            account_id,
            external_id,
            {
                "status": SubscriptionStatus.active,
                "stripe_subscription_id": "sub_activated_123",
                "payment_method": PaymentMethod.invoice,
            },
            force_update=True,
        )

        # Assert — ProjectSubscriptions updated
        proj_sub_repo_instance = MockProjSubRepo.return_value
        assert proj_sub_repo_instance.update_project_subscription.call_count == 2
        for ps in mock_project_subscriptions:
            proj_sub_repo_instance.update_project_subscription.assert_any_call(
                id=ps.id,
                stripe_subscription_id="sub_activated_123",
                status=SubscriptionStatus.active,
            )

        # Assert — session committed
        mock_session.commit.assert_called_once()

        # Assert — notification sent
        mock_send_notif.assert_called_once()

        assert result == updated_sub

    @patch(_SEND_NOTIF)
    @patch(_UPDATE_ACCT_SUB)
    @patch(_STRIPE_SUB)
    @patch(_GRANT_CREDIT)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_grants_credits_after_stripe_subscription_created(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_grant_credit: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_update_acct_sub: MagicMock,
        mock_send_notif: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )
        updated_sub = MagicMock()
        updated_sub.subscription_plan = mock_subscription.subscription_plan
        mock_update_acct_sub.return_value = updated_sub

        activate_subscription_without_payment_method(
            session=mock_session,
            context=mock_context,
            account_id=account_id,
            external_id=external_id,
            grant_credit_amount_cents=50000,
            currency="usd",
        )

        # Assert — credits granted after Stripe subscription creation
        mock_grant_credit.assert_called_once_with(
            account=mock_account,
            credit_amount_cents=50000,
            currency="usd",
            description="Credit grant at subscription activation",
            issued_by="admin@example.com",
            metadata={
                "issued_via": "activate_subscription_without_payment_method",
                "request_source": "admin_activation",
                "subscription_external_id": str(external_id),
            },
            idempotency_key=f"activate-credit-{external_id}",
        )
        mock_stripe_sub_module.create_subscription_direct.assert_called_once()

    @patch(_SEND_NOTIF)
    @patch(_UPDATE_ACCT_SUB)
    @patch(_STRIPE_SUB)
    @patch(_GRANT_CREDIT)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_stripe_creation_happens_before_credit_grant(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_grant_credit: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_update_acct_sub: MagicMock,
        mock_send_notif: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        call_order: list[str] = []

        def record_stripe_create(**kwargs: object) -> MagicMock:
            call_order.append("stripe_create")
            return mock_stripe_subscription

        def record_grant_credit(**kwargs: object) -> None:
            call_order.append("grant_credit")

        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.side_effect = (
            record_stripe_create
        )
        mock_grant_credit.side_effect = record_grant_credit
        updated_sub = MagicMock()
        updated_sub.subscription_plan = None
        mock_update_acct_sub.return_value = updated_sub

        activate_subscription_without_payment_method(
            session=mock_session,
            context=mock_context,
            account_id=account_id,
            external_id=external_id,
            grant_credit_amount_cents=50000,
        )

        assert call_order == [
            "stripe_create",
            "grant_credit",
        ], f"Expected stripe_create before grant_credit, got: {call_order}"

    @patch(_SEND_NOTIF)
    @patch(_UPDATE_ACCT_SUB)
    @patch(_STRIPE_SUB)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_applies_account_coupon_when_present(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_update_acct_sub: MagicMock,
        mock_send_notif: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        mock_account.stripe_coupon_id = "coupon_50off"
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )
        updated_sub = MagicMock()
        updated_sub.subscription_plan = mock_subscription.subscription_plan
        mock_update_acct_sub.return_value = updated_sub

        activate_subscription_without_payment_method(
            session=mock_session,
            context=mock_context,
            account_id=account_id,
            external_id=external_id,
        )

        create_call_kwargs = (
            mock_stripe_sub_module.create_subscription_direct.call_args[1]
        )
        assert create_call_kwargs["coupon_id"] == "coupon_50off"

    @patch(_SEND_NOTIF)
    @patch(_UPDATE_ACCT_SUB)
    @patch(_STRIPE_SUB)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_skips_notification_when_no_plan(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_update_acct_sub: MagicMock,
        mock_send_notif: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )
        updated_sub = MagicMock()
        updated_sub.subscription_plan = None  # no plan linked
        mock_update_acct_sub.return_value = updated_sub

        activate_subscription_without_payment_method(
            session=mock_session,
            context=mock_context,
            account_id=account_id,
            external_id=external_id,
        )

        mock_send_notif.assert_not_called()

    @patch(_SEND_NOTIF)
    @patch(_UPDATE_ACCT_SUB)
    @patch(_STRIPE_SUB)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_future_start_date_sets_trialing_and_trial_end(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_update_acct_sub: MagicMock,
        mock_send_notif: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        # Set start_date to the future
        future_start = datetime.now(UTC) + timedelta(days=30)
        mock_subscription.start_date = future_start

        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )
        updated_sub = MagicMock()
        updated_sub.subscription_plan = None
        mock_update_acct_sub.return_value = updated_sub

        activate_subscription_without_payment_method(
            session=mock_session,
            context=mock_context,
            account_id=account_id,
            external_id=external_id,
        )

        # Stripe subscription should be created with trial_end
        create_kwargs = mock_stripe_sub_module.create_subscription_direct.call_args[1]
        assert create_kwargs["trial_end"] == int(future_start.timestamp())

        # AccountSubscription should be set to trialing, not active
        update_call_args = mock_update_acct_sub.call_args
        assert update_call_args[0][4]["status"] == SubscriptionStatus.trialing

        # ProjectSubscriptions should also be trialing
        proj_sub_repo = MockProjSubRepo.return_value
        for ps_call in proj_sub_repo.update_project_subscription.call_args_list:
            assert ps_call[1]["status"] == SubscriptionStatus.trialing


class TestActivateSubscriptionValidation:
    """Tests for input validation — no Stripe calls made."""

    def test_raises_if_negative_credit_amount(
        self,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> None:
        with pytest.raises(ValueError, match="must not be negative"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
                grant_credit_amount_cents=-100,
            )

    @patch(_ACCT_SUB_REPO)
    def test_raises_if_subscription_not_found(
        self,
        MockAcctSubRepo: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = None

        with pytest.raises(ValueError, match="not found"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )

    @patch(_ACCT_SUB_REPO)
    def test_raises_if_subscription_already_active(
        self,
        MockAcctSubRepo: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_subscription: MagicMock,
    ) -> None:
        mock_subscription.status = SubscriptionStatus.active
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )

        with pytest.raises(ValueError, match="already active"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )

    @patch(_ACCT_SUB_REPO)
    def test_raises_if_subscription_not_pending(
        self,
        MockAcctSubRepo: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_subscription: MagicMock,
    ) -> None:
        mock_subscription.status = SubscriptionStatus.cancelled
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )

        with pytest.raises(ValueError, match="must be in pending status"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )

    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_raises_if_account_not_found(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_subscription: MagicMock,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        mock_acct_service.get_account_by_id.return_value = None

        with pytest.raises(ValueError, match=r"Account .* not found"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )

    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_raises_if_no_stripe_customer(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
    ) -> None:
        mock_account.stripe_customer_id = None
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        mock_acct_service.get_account_by_id.return_value = mock_account

        with pytest.raises(ValueError, match="does not have a Stripe customer"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )

    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_raises_if_no_project_subscriptions(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            []
        )

        with pytest.raises(RuntimeError, match="No project subscriptions found"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )

    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_raises_if_no_valid_price_ids(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
    ) -> None:
        # Project subscription with no price IDs
        ps = MagicMock()
        ps.base_price_id = None
        ps.call_price_id = None
        ps.order_price_id = None
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = [
            ps
        ]

        with pytest.raises(RuntimeError, match="No valid price IDs"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
            )


class TestActivateSubscriptionCreditGrantFailure:
    """Tests for credit grant failure after Stripe subscription creation."""

    @patch(_GRANT_CREDIT)
    @patch(_STRIPE_SUB)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_raises_if_credit_grant_fails_after_stripe_creation(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_grant_credit: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )
        mock_grant_credit.side_effect = Exception("Stripe credit grant failed")

        with pytest.raises(Exception, match="Stripe credit grant failed"):
            activate_subscription_without_payment_method(
                session=mock_session,
                context=mock_context,
                account_id=account_id,
                external_id=external_id,
                grant_credit_amount_cents=50000,
            )

        # Stripe subscription was created before credit grant failed
        mock_stripe_sub_module.create_subscription_direct.assert_called_once()

    @patch(_STRIPE_SUB)
    @patch(_ACCT_SERVICE)
    @patch(_PROJ_SUB_REPO)
    @patch(_ACCT_SUB_REPO)
    def test_skips_credit_grant_when_zero(
        self,
        MockAcctSubRepo: MagicMock,
        MockProjSubRepo: MagicMock,
        mock_acct_service: MagicMock,
        mock_stripe_sub_module: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        mock_account: MagicMock,
        mock_subscription: MagicMock,
        mock_project_subscriptions: list[MagicMock],
        mock_stripe_subscription: MagicMock,
    ) -> None:
        MockAcctSubRepo.return_value.get_account_subscription.return_value = (
            mock_subscription
        )
        MockProjSubRepo.return_value.get_project_subscriptions_by_subscription_id.return_value = (
            mock_project_subscriptions
        )
        mock_acct_service.get_account_by_id.return_value = mock_account
        mock_stripe_sub_module.create_subscription_direct.return_value = (
            mock_stripe_subscription
        )

        with patch(_UPDATE_ACCT_SUB) as mock_update, patch(_SEND_NOTIF):
            updated_sub = MagicMock()
            updated_sub.subscription_plan = None
            mock_update.return_value = updated_sub

            with patch(_GRANT_CREDIT) as mock_grant:
                activate_subscription_without_payment_method(
                    session=mock_session,
                    context=mock_context,
                    account_id=account_id,
                    external_id=external_id,
                    grant_credit_amount_cents=0,
                )

                mock_grant.assert_not_called()
