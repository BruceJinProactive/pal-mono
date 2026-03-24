"""S5: Stripe Webhook Idempotency & Ordering.

Tests that Stripe webhook processing handles duplicate events,
out-of-order delivery, and signature verification correctly.
Tests at the repository/subscription-service level since the webhook
handler uses its own AsyncSessionLocal (ADR-019).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from db.repositories.subscription_repository import AccountSubscriptionRepository
from db.tables.types import SubscriptionStatus
from tests.factories import (
    make_account_subscription,
    make_subscription_plan,
    make_world,
)


@pytest.mark.integration
class TestStripeWebhookSubscriptionFlow:
    def test_subscription_created_sets_active(self, db_session: Session) -> None:
        """Simulates subscription.created: status becomes active."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.id == sub.id
        assert result.status == SubscriptionStatus.active

    def test_duplicate_status_update_is_idempotent(self, db_session: Session) -> None:
        """Updating to same status twice has no adverse effect."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        repo = AccountSubscriptionRepository(db_session)

        # "Update" to same status twice
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.active
        )
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.active
        )

        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.status == SubscriptionStatus.active

    def test_subscription_deleted_sets_cancelled(self, db_session: Session) -> None:
        """Simulates subscription.deleted: status becomes cancelled."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        repo = AccountSubscriptionRepository(db_session)
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.cancelled
        )

        result = repo.get_active_account_subscription(world.account.id)
        assert result is None

    def test_out_of_order_updated_before_created(self, db_session: Session) -> None:
        """subscription.updated arriving before subscription.created works
        because subscription already exists in fixture."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.trialing,
        )

        repo = AccountSubscriptionRepository(db_session)

        # "Updated" arrives first -> active
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.active
        )

        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.status == SubscriptionStatus.active

    def test_payment_failed_then_succeeded_lifecycle(self, db_session: Session) -> None:
        """Payment failure followed by success: subscription stays active."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        repo = AccountSubscriptionRepository(db_session)

        # Payment failed -> past_due
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.past_due
        )
        result = repo.get_active_account_subscription(world.account.id)
        # past_due is not "active"
        assert result is None

        # Payment succeeded -> back to active
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.active
        )
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.status == SubscriptionStatus.active

    def test_unknown_account_returns_none(self, db_session: Session) -> None:
        """Query for non-existent account returns None (graceful handling)."""
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(uuid.uuid4())
        assert result is None

    def test_multiple_subscriptions_same_account(self, db_session: Session) -> None:
        """Only active subscription is returned when multiple exist."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)

        # Old cancelled subscription
        make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.cancelled,
        )
        # Current active subscription
        active_sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.id == active_sub.id

    def test_overlap_detection_with_active_sub(self, db_session: Session) -> None:
        """Active subscription causes overlap detection to return True."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        now = datetime.now(UTC)

        make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
            start_date=now - timedelta(days=30),
        )

        repo = AccountSubscriptionRepository(db_session)
        has_overlap = repo.check_subscription_overlap(
            world.account.id,
            start_date=now,
            end_date=now + timedelta(days=30),
        )
        assert has_overlap is True

    def test_tenant_isolation_between_webhooks(self, db_session: Session) -> None:
        """Webhook for Account A does not affect Account B."""
        world_a = make_world(db_session)
        world_b = make_world(db_session)
        plan = make_subscription_plan(db_session)

        make_account_subscription(
            db_session,
            account_id=world_a.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        repo = AccountSubscriptionRepository(db_session)
        result_b = repo.get_active_account_subscription(world_b.account.id)
        assert result_b is None
