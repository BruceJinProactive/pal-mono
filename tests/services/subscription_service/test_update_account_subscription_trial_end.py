"""Tests for trial_end handling in update_account_subscription().

Validates the Stripe-pattern trial extension: accepting an absolute trial_end
datetime that sets start_date and manages trial state.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from db.tables.subscriptions import SubscriptionStatus
from services.subscription_service._subscription import update_account_subscription


class _FakeColumn:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeTable:
    """Minimal stand-in for SQLAlchemy __table__ used by the service's clone logic."""

    columns = [
        _FakeColumn("external_id"),
        _FakeColumn("account_id"),
        _FakeColumn("version"),
        _FakeColumn("status"),
        _FakeColumn("trial_start_date"),
        _FakeColumn("start_date"),
        _FakeColumn("end_date"),
        _FakeColumn("payment_method"),
        _FakeColumn("stripe_subscription_id"),
        _FakeColumn("subscription_plan_id"),
    ]


class FakeSubscription:
    """Minimal subscription class that satisfies type(instance).__table__.columns."""

    __table__ = _FakeTable()

    id: uuid.UUID
    external_id: uuid.UUID
    account_id: uuid.UUID
    version: int
    is_valid: bool
    status: SubscriptionStatus
    trial_start_date: datetime | None
    start_date: datetime
    end_date: datetime | None
    payment_method: str
    stripe_subscription_id: str | None
    subscription_plan_id: uuid.UUID

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.commit = MagicMock()
    return session


@pytest.fixture
def mock_context() -> MagicMock:
    context = MagicMock()
    context.email = "admin@test.com"
    return context


@pytest.fixture
def trialing_subscription() -> FakeSubscription:
    return FakeSubscription(
        id=uuid.uuid4(),
        external_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        version=1,
        is_valid=True,
        status=SubscriptionStatus.trialing,
        trial_start_date=datetime.now(UTC) - timedelta(days=7),
        start_date=datetime.now(UTC) + timedelta(days=7),
        end_date=None,
        payment_method="card",
        stripe_subscription_id=None,
        subscription_plan_id=uuid.uuid4(),
    )


@pytest.fixture
def active_subscription() -> FakeSubscription:
    return FakeSubscription(
        id=uuid.uuid4(),
        external_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        version=1,
        is_valid=True,
        status=SubscriptionStatus.active,
        trial_start_date=None,
        start_date=datetime.now(UTC) - timedelta(days=30),
        end_date=None,
        payment_method="card",
        stripe_subscription_id="sub_123",
        subscription_plan_id=uuid.uuid4(),
    )


class TestTrialEndOnTrialingSubscription:
    """trial_end on a subscription already in trialing status."""

    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.AccountSubscriptionRepository")
    def test_trial_end_sets_start_date(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        trialing_subscription: FakeSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=21)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_account_subscription.return_value = trialing_subscription
        mock_repo.create_account_subscription.return_value = trialing_subscription
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_account_subscription(
            session=mock_session,
            context=mock_context,
            account_id=trialing_subscription.account_id,
            external_id=trialing_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        # The new subscription should have start_date set to trial_end
        created_sub = mock_repo.create_account_subscription.call_args[0][0]
        assert created_sub.start_date == trial_end

    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.AccountSubscriptionRepository")
    def test_trial_end_preserves_existing_trial_start_date(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        trialing_subscription: FakeSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=21)
        original_trial_start = trialing_subscription.trial_start_date
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_account_subscription.return_value = trialing_subscription
        mock_repo.create_account_subscription.return_value = trialing_subscription
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_account_subscription(
            session=mock_session,
            context=mock_context,
            account_id=trialing_subscription.account_id,
            external_id=trialing_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        # trial_start_date should not be overwritten since it already exists
        created_sub = mock_repo.create_account_subscription.call_args[0][0]
        assert created_sub.trial_start_date == original_trial_start


class TestTrialEndOnActiveSubscription:
    """trial_end on an active subscription with no existing trial."""

    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.AccountSubscriptionRepository")
    def test_trial_end_sets_trial_start_date_when_missing(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_subscription: FakeSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=14)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_account_subscription.return_value = active_subscription
        mock_repo.create_account_subscription.return_value = active_subscription
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        before = datetime.now(UTC)
        update_account_subscription(
            session=mock_session,
            context=mock_context,
            account_id=active_subscription.account_id,
            external_id=active_subscription.external_id,
            update_data={"trial_end": trial_end},
        )
        after = datetime.now(UTC)

        created_sub = mock_repo.create_account_subscription.call_args[0][0]
        # trial_start_date should be set to approximately now
        assert created_sub.trial_start_date >= before
        assert created_sub.trial_start_date <= after

    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.AccountSubscriptionRepository")
    def test_trial_end_sets_status_to_trialing_when_active(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_subscription: FakeSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=14)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_account_subscription.return_value = active_subscription
        mock_repo.create_account_subscription.return_value = active_subscription
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_account_subscription(
            session=mock_session,
            context=mock_context,
            account_id=active_subscription.account_id,
            external_id=active_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        created_sub = mock_repo.create_account_subscription.call_args[0][0]
        assert created_sub.status == SubscriptionStatus.trialing


class TestTrialEndStripeSync:
    """Verify trial_end is synced to Stripe."""

    @patch("services.subscription_service._subscription.stripe")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.AccountSubscriptionRepository")
    def test_trial_end_calls_stripe_modify(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_stripe: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        active_subscription: FakeSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=14)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_account_subscription.return_value = active_subscription
        # Return a subscription with stripe_subscription_id
        created_sub = MagicMock()
        created_sub.stripe_subscription_id = "sub_123"
        mock_repo.create_account_subscription.return_value = created_sub
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_account_subscription(
            session=mock_session,
            context=mock_context,
            account_id=active_subscription.account_id,
            external_id=active_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        mock_stripe.Subscription.modify.assert_called_once_with(
            "sub_123",
            trial_end=int(trial_end.timestamp()),
        )

    @patch("services.subscription_service._subscription.stripe")
    @patch("services.subscription_service._subscription.change_log_context")
    @patch("services.subscription_service._subscription.AccountSubscriptionRepository")
    def test_trial_end_skips_stripe_when_no_stripe_id(
        self,
        mock_repo_cls: MagicMock,
        mock_changelog: MagicMock,
        mock_stripe: MagicMock,
        mock_session: MagicMock,
        mock_context: MagicMock,
        trialing_subscription: FakeSubscription,
    ) -> None:
        trial_end = datetime.now(UTC) + timedelta(days=21)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_account_subscription.return_value = trialing_subscription
        # Return a subscription without stripe_subscription_id
        created_sub = MagicMock()
        created_sub.stripe_subscription_id = None
        mock_repo.create_account_subscription.return_value = created_sub
        mock_changelog.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_changelog.return_value.__exit__ = MagicMock(return_value=False)

        update_account_subscription(
            session=mock_session,
            context=mock_context,
            account_id=trialing_subscription.account_id,
            external_id=trialing_subscription.external_id,
            update_data={"trial_end": trial_end},
        )

        mock_stripe.Subscription.modify.assert_not_called()


class TestTrialEndSchemaValidation:
    """Schema-level validation for trial_end field."""

    def test_trial_end_and_start_date_conflict_raises(self) -> None:
        from api.schemas.admin.subscription import UpdateAccountSubscriptionRequest

        with pytest.raises(
            ValueError, match="Cannot specify both trial_end and start_date"
        ):
            UpdateAccountSubscriptionRequest(
                trial_end=datetime.now(UTC) + timedelta(days=14),
                start_date=datetime.now(UTC) + timedelta(days=7),
            )

    def test_trial_end_alone_is_valid(self) -> None:
        from api.schemas.admin.subscription import UpdateAccountSubscriptionRequest

        req = UpdateAccountSubscriptionRequest(
            trial_end=datetime.now(UTC) + timedelta(days=14),
        )
        assert req.trial_end is not None
        assert req.start_date is None
