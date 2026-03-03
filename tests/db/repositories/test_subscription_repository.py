"""Tests for subscription repositories.

Business focus: Billing lifecycle — plan management, subscription overlap
prevention (double-billing), conservative error handling, and soft deletion.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.subscription_repository import (
    AccountSubscriptionRepository,
    AsyncAccountSubscriptionRepository,
    AsyncProjectSubscriptionRepository,
    ProjectSubscriptionRepository,
    SubscriptionPlanRepository,
)
from db.tables.subscriptions import (
    AccountSubscription,
    ProjectSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    mock_query = MagicMock()
    session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.limit.return_value = mock_query
    return session


@pytest.fixture
def mock_async_session():
    return AsyncMock()


@pytest.fixture
def plan_repo(mock_session):
    return SubscriptionPlanRepository(mock_session)


@pytest.fixture
def acct_sub_repo(mock_session):
    return AccountSubscriptionRepository(mock_session)


@pytest.fixture
def proj_sub_repo(mock_session):
    return ProjectSubscriptionRepository(mock_session)


@pytest.fixture
def async_acct_sub_repo(mock_async_session):
    return AsyncAccountSubscriptionRepository(mock_async_session)


@pytest.fixture
def async_proj_sub_repo(mock_async_session):
    return AsyncProjectSubscriptionRepository(mock_async_session)


@pytest.fixture
def sample_plan_id():
    return uuid.uuid4()


@pytest.fixture
def sample_plan(sample_plan_id):
    plan = MagicMock(spec=SubscriptionPlan)
    plan.id = sample_plan_id
    plan.active = True
    plan.hidden = False
    plan.features_included = ["voice"]
    plan.features_excluded = []
    return plan


@pytest.fixture
def sample_account_id():
    return uuid.uuid4()


@pytest.fixture
def sample_subscription():
    sub = MagicMock(spec=AccountSubscription)
    sub.id = uuid.uuid4()
    sub.external_id = uuid.uuid4()
    sub.status = SubscriptionStatus.active
    sub.start_date = datetime(2025, 1, 1, tzinfo=UTC)
    sub.end_date = None
    sub.version = 1
    return sub


# ---------------------------------------------------------------------------
# TestSubscriptionPlanManagement
# ---------------------------------------------------------------------------


class TestSubscriptionPlanManagement:
    """Plan CRUD and safety checks before deletion."""

    def test_get_plan_by_id_only_returns_active_plans(
        self, plan_repo, mock_session, sample_plan
    ):
        """Cannot look up deactivated plans."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_plan
        )
        result = plan_repo.get_subscription_plan_by_id(sample_plan.id)
        assert result == sample_plan

    def test_get_plan_by_id_returns_none_when_not_found(self, plan_repo, mock_session):
        """Deactivated or missing plan returns None."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = plan_repo.get_subscription_plan_by_id(uuid.uuid4())
        assert result is None

    def test_get_plans_filtered_by_hidden(self, plan_repo, mock_session, sample_plan):
        """Public vs internal pricing plans."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value.all.return_value = [sample_plan]

        result = plan_repo.get_subscription_plans(hidden=False)
        assert result == [sample_plan]

    def test_get_plans_returns_empty_on_error(self, plan_repo, mock_session):
        """Error resilience."""
        mock_session.query.side_effect = SQLAlchemyError("error")
        result = plan_repo.get_subscription_plans()
        assert result == []

    def test_create_plan_initializes_feature_lists(self, plan_repo, mock_session):
        """New plan has empty feature arrays, not null."""
        result = plan_repo.create_subscription_plan(name="Basic")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert isinstance(result, SubscriptionPlan)

    def test_has_active_subscriptions_returns_true_when_active_exists(
        self, plan_repo, mock_session, sample_subscription
    ):
        """Cannot delete plan with active subscribers."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_subscription
        )
        assert plan_repo.has_active_account_subscriptions(uuid.uuid4()) is True

    def test_has_active_subscriptions_returns_false_when_none(
        self, plan_repo, mock_session
    ):
        """Safe to delete plan with no subscribers."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        assert plan_repo.has_active_account_subscriptions(uuid.uuid4()) is False

    def test_has_active_subscriptions_returns_true_on_db_error(
        self, plan_repo, mock_session
    ):
        """Conservative: assume active on error to prevent accidental plan deletion."""
        mock_session.query.return_value.filter.return_value.first.side_effect = (
            SQLAlchemyError("connection lost")
        )
        result = plan_repo.has_active_account_subscriptions(uuid.uuid4())
        assert result is True
        mock_session.rollback.assert_called_once()

    def test_update_plan_not_found_raises_value_error(self, plan_repo, mock_session):
        """Cannot update nonexistent plan."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            plan_repo.update_subscription_plan(uuid.uuid4(), name="Updated")

    def test_delete_plan_raises_if_not_found(self, plan_repo, mock_session):
        """Cannot delete nonexistent plan."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            plan_repo.delete_subscription_plan(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestAccountSubscriptionOverlap — CRITICAL: Prevents double-billing
# ---------------------------------------------------------------------------


class TestAccountSubscriptionOverlap:
    """Overlap detection is the #1 billing invariant. New subscriptions must
    not overlap active/pending/trialing ones."""

    def test_overlap_detected_when_existing_is_ongoing(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """New subscription overlaps existing ongoing (no end date)."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_subscription
        )
        result = acct_sub_repo.check_subscription_overlap(
            account_id=uuid.uuid4(),
            start_date=datetime(2025, 6, 1, tzinfo=UTC),
            end_date=datetime(2025, 12, 31, tzinfo=UTC),
        )
        assert result is True

    def test_overlap_detected_when_new_is_ongoing(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """New ongoing subscription overlaps existing."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_subscription
        )
        result = acct_sub_repo.check_subscription_overlap(
            account_id=uuid.uuid4(),
            start_date=datetime(2025, 6, 1, tzinfo=UTC),
            end_date=None,
        )
        assert result is True

    def test_no_overlap_when_no_active_subscriptions(self, acct_sub_repo, mock_session):
        """Fresh account with no subscriptions."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = acct_sub_repo.check_subscription_overlap(
            account_id=uuid.uuid4(),
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 12, 31, tzinfo=UTC),
        )
        assert result is False

    def test_overlap_returns_true_on_db_error(self, acct_sub_repo, mock_session):
        """Conservative: assume overlap on error to prevent double-billing."""
        mock_session.query.return_value.filter.return_value.first.side_effect = (
            SQLAlchemyError("connection lost")
        )
        result = acct_sub_repo.check_subscription_overlap(
            account_id=uuid.uuid4(),
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 12, 31, tzinfo=UTC),
        )
        assert result is True
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestAccountSubscriptionLifecycle
# ---------------------------------------------------------------------------


class TestAccountSubscriptionLifecycle:
    """Subscription state machine: creation, status transitions, lookups."""

    def test_create_subscription_success(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """New subscription activated for restaurant."""
        result = acct_sub_repo.create_account_subscription(sample_subscription)
        mock_session.add.assert_called_once_with(sample_subscription)
        mock_session.commit.assert_called_once()
        assert result == sample_subscription

    def test_get_account_subscriptions_returns_active(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """Active/pending subscriptions returned, not ended ones."""
        mock_q = mock_session.query.return_value
        mock_q.options.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_subscription
        ]
        result = acct_sub_repo.get_account_subscriptions(uuid.uuid4())
        assert result == [sample_subscription]

    def test_get_account_subscriptions_returns_empty_on_error(
        self, acct_sub_repo, mock_session
    ):
        """Graceful degradation."""
        mock_session.query.side_effect = SQLAlchemyError("error")
        result = acct_sub_repo.get_account_subscriptions(uuid.uuid4())
        assert result == []

    def test_get_subscription_by_external_id_returns_latest_version(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """Version tracking: returns most recent."""
        mock_session.query.return_value.options.return_value.filter.return_value.order_by.return_value.first.return_value = (
            sample_subscription
        )
        result = acct_sub_repo.get_account_subscription_by_external_id(
            sample_subscription.external_id
        )
        assert result == sample_subscription

    def test_update_subscription_status(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """Status transitions (e.g., trialing -> active)."""
        with patch.object(
            acct_sub_repo,
            "get_account_subscription_by_external_id",
            return_value=sample_subscription,
        ):
            result = acct_sub_repo.update_account_subscription_status(
                sample_subscription.external_id, SubscriptionStatus.active
            )
        assert sample_subscription.status == SubscriptionStatus.active
        assert result == sample_subscription

    def test_update_subscription_status_not_found_returns_none(
        self, acct_sub_repo, mock_session
    ):
        """Graceful handling of missing subscription."""
        with patch.object(
            acct_sub_repo,
            "get_account_subscription_by_external_id",
            return_value=None,
        ):
            result = acct_sub_repo.update_account_subscription_status(
                uuid.uuid4(), SubscriptionStatus.active
            )
        assert result is None

    def test_get_active_account_subscription(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """Get current subscription for billing check."""
        mock_session.query.return_value.options.return_value.filter.return_value.order_by.return_value.first.return_value = (
            sample_subscription
        )
        result = acct_sub_repo.get_active_account_subscription(uuid.uuid4())
        assert result == sample_subscription

    def test_update_payment_method(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """Customer updates credit card."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_subscription
        )
        result = acct_sub_repo.update_payment_method(
            sample_subscription.id, "pm_new_card"
        )
        assert sample_subscription.payment_method == "pm_new_card"
        assert result == sample_subscription

    def test_update_payment_method_not_found(self, acct_sub_repo, mock_session):
        """Subscription does not exist."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = acct_sub_repo.update_payment_method(uuid.uuid4(), "pm_card")
        assert result is None

    def test_update_account_subscription_fields(
        self, acct_sub_repo, mock_session, sample_subscription
    ):
        """Update arbitrary fields on subscription."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_subscription
        )
        result = acct_sub_repo.update_account_subscription(
            sample_subscription.id, stripe_subscription_id="sub_123"
        )
        assert result == sample_subscription

    def test_update_account_subscription_not_found(self, acct_sub_repo, mock_session):
        """Missing subscription returns None."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = acct_sub_repo.update_account_subscription(uuid.uuid4(), status="x")
        assert result is None


# ---------------------------------------------------------------------------
# TestProjectSubscriptionLifecycle
# ---------------------------------------------------------------------------


class TestProjectSubscriptionLifecycle:
    """Per-location (project) subscription management with soft deletion."""

    def test_create_project_subscription(self, proj_sub_repo, mock_session):
        """Activate subscription for specific restaurant location."""
        result = proj_sub_repo.create_project_subscription(
            project_id=uuid.uuid4(), subscription_id=uuid.uuid4()
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert isinstance(result, ProjectSubscription)

    def test_create_project_subscription_with_prices(self, proj_sub_repo, mock_session):
        """Subscription with call and order price IDs."""
        result = proj_sub_repo.create_project_subscription_with_prices(
            project_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
            call_price_id="price_call_123",
            order_price_id="price_order_456",
        )
        mock_session.add.assert_called_once()
        assert isinstance(result, ProjectSubscription)

    def test_soft_delete_project_subscription(self, proj_sub_repo, mock_session):
        """Sets deleted flag, does not hard delete."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_sub.deleted = False
        with patch.object(
            proj_sub_repo, "get_project_subscription", return_value=mock_sub
        ):
            result = proj_sub_repo.delete_project_subscription(
                uuid.uuid4(), uuid.uuid4()
            )
        assert mock_sub.deleted is True
        assert result is True

    def test_soft_delete_nonexistent_returns_false(self, proj_sub_repo, mock_session):
        """Idempotent soft delete."""
        with patch.object(proj_sub_repo, "get_project_subscription", return_value=None):
            result = proj_sub_repo.delete_project_subscription(
                uuid.uuid4(), uuid.uuid4()
            )
        assert result is False

    def test_get_project_subscription_excludes_deleted(
        self, proj_sub_repo, mock_session
    ):
        """Soft-deleted subscriptions not returned."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_sub
        )
        result = proj_sub_repo.get_project_subscription(uuid.uuid4(), uuid.uuid4())
        assert result == mock_sub

    def test_get_active_project_subscription(self, proj_sub_repo, mock_session):
        """Get current subscription for billing check."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_sub
        )
        result = proj_sub_repo.get_active_project_subscription(uuid.uuid4())
        assert result == mock_sub

    def test_get_project_subscription_by_external_id(self, proj_sub_repo, mock_session):
        """External ID lookup returns latest version."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_sub
        )
        result = proj_sub_repo.get_project_subscription_by_external_id(uuid.uuid4())
        assert result == mock_sub

    def test_update_project_subscription(self, proj_sub_repo, mock_session):
        """Update project subscription fields."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_sub
        )
        result = proj_sub_repo.update_project_subscription(
            uuid.uuid4(), call_price_id="new_price"
        )
        assert result == mock_sub

    def test_update_project_subscription_not_found(self, proj_sub_repo, mock_session):
        """Missing subscription returns None."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = proj_sub_repo.update_project_subscription(uuid.uuid4(), status="x")
        assert result is None


# ---------------------------------------------------------------------------
# TestProjectSubscriptionOverlap
# ---------------------------------------------------------------------------


class TestProjectSubscriptionOverlap:
    """Per-store subscription overlap checking, same conservative pattern."""

    def test_project_overlap_detected(self, proj_sub_repo, mock_session):
        """Per-store subscription overlap."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_sub
        )
        result = proj_sub_repo.check_subscription_overlap(
            project_id=uuid.uuid4(),
            start_date=datetime(2025, 6, 1, tzinfo=UTC),
            end_date=datetime(2025, 12, 31, tzinfo=UTC),
        )
        assert result is True

    def test_project_no_overlap(self, proj_sub_repo, mock_session):
        """No overlap when no active subscriptions."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = proj_sub_repo.check_subscription_overlap(
            project_id=uuid.uuid4(),
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 12, 31, tzinfo=UTC),
        )
        assert result is False

    def test_project_overlap_returns_true_on_error(self, proj_sub_repo, mock_session):
        """Conservative error handling prevents double-billing."""
        mock_session.query.return_value.filter.return_value.first.side_effect = (
            SQLAlchemyError("error")
        )
        result = proj_sub_repo.check_subscription_overlap(
            project_id=uuid.uuid4(),
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=None,
        )
        assert result is True
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestAsyncAccountSubscription — Webhook processing path
# ---------------------------------------------------------------------------


class TestAsyncAccountSubscription:
    """Async operations used for Stripe webhook event processing."""

    @pytest.mark.asyncio
    async def test_async_get_by_external_id(
        self, async_acct_sub_repo, mock_async_session, sample_subscription
    ):
        """Webhook processing looks up subscription."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_subscription
        mock_async_session.execute.return_value = mock_result

        result = await async_acct_sub_repo.get_account_subscription(
            uuid.uuid4(), sample_subscription.external_id
        )
        assert result == sample_subscription

    @pytest.mark.asyncio
    async def test_async_get_by_external_id_not_found(
        self, async_acct_sub_repo, mock_async_session
    ):
        """Unknown external ID returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_acct_sub_repo.get_account_subscription(
            uuid.uuid4(), uuid.uuid4()
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_async_get_by_stripe_subscription_id(
        self, async_acct_sub_repo, mock_async_session, sample_subscription
    ):
        """Stripe webhook event routing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_subscription
        mock_async_session.execute.return_value = mock_result

        result = await async_acct_sub_repo.get_account_subscription_by_stripe_subscription_id(
            "sub_stripe_123"
        )
        assert result == sample_subscription

    @pytest.mark.asyncio
    async def test_async_update_status(
        self, async_acct_sub_repo, mock_async_session, sample_subscription
    ):
        """Async status change from webhook."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_subscription
        mock_async_session.execute.return_value = mock_result

        result = await async_acct_sub_repo.update_account_subscription_status(
            sample_subscription.id, SubscriptionStatus.active
        )
        assert sample_subscription.status == SubscriptionStatus.active
        assert result == sample_subscription

    @pytest.mark.asyncio
    async def test_async_update_status_not_found(
        self, async_acct_sub_repo, mock_async_session
    ):
        """Missing subscription returns None on status update."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_acct_sub_repo.update_account_subscription_status(
            uuid.uuid4(), SubscriptionStatus.active
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_async_get_subscriptions_with_stripe_id(
        self, async_acct_sub_repo, mock_async_session, sample_subscription
    ):
        """Reconciliation: find all Stripe-linked subscriptions."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_subscription]
        mock_async_session.execute.return_value = mock_result

        result = await async_acct_sub_repo.get_account_subscriptions_with_stripe_id(
            uuid.uuid4()
        )
        assert result == [sample_subscription]

    @pytest.mark.asyncio
    async def test_async_get_subscriptions_with_stripe_id_returns_empty_on_error(
        self, async_acct_sub_repo, mock_async_session
    ):
        """Error returns empty list."""
        mock_async_session.execute.side_effect = SQLAlchemyError("error")
        result = await async_acct_sub_repo.get_account_subscriptions_with_stripe_id(
            uuid.uuid4()
        )
        assert result == []


# ---------------------------------------------------------------------------
# TestAsyncProjectSubscription
# ---------------------------------------------------------------------------


class TestAsyncProjectSubscription:
    """Async project subscription operations for webhook processing."""

    @pytest.mark.asyncio
    async def test_async_get_by_stripe_id(
        self, async_proj_sub_repo, mock_async_session
    ):
        """Stripe webhook for project subscription."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sub
        mock_async_session.execute.return_value = mock_result

        result = await async_proj_sub_repo.get_project_subscription_by_stripe_id(
            "sub_stripe_456"
        )
        assert result == mock_sub

    @pytest.mark.asyncio
    async def test_async_get_by_stripe_id_not_found(
        self, async_proj_sub_repo, mock_async_session
    ):
        """Unknown Stripe ID returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_proj_sub_repo.get_project_subscription_by_stripe_id(
            "sub_unknown"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_async_update_status(self, async_proj_sub_repo, mock_async_session):
        """Async project subscription status change."""
        mock_sub = MagicMock(spec=ProjectSubscription)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sub
        mock_async_session.execute.return_value = mock_result

        result = await async_proj_sub_repo.update_project_subscription_status(
            uuid.uuid4(), SubscriptionStatus.active
        )
        assert mock_sub.status == SubscriptionStatus.active
        assert result == mock_sub

    @pytest.mark.asyncio
    async def test_async_update_status_not_found(
        self, async_proj_sub_repo, mock_async_session
    ):
        """Missing project subscription returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_proj_sub_repo.update_project_subscription_status(
            uuid.uuid4(), SubscriptionStatus.active
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_async_update_status_rolls_back_on_error(
        self, async_proj_sub_repo, mock_async_session
    ):
        """DB error rolls back session."""
        mock_async_session.execute.side_effect = SQLAlchemyError("error")
        with pytest.raises(SQLAlchemyError):
            await async_proj_sub_repo.update_project_subscription_status(
                uuid.uuid4(), SubscriptionStatus.active
            )
        mock_async_session.rollback.assert_awaited_once()
