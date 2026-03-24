"""S10: Subscription Gating Integration Tests.

Tests that subscription status queries return correct results for
active, expired, cancelled, trialing, and missing subscriptions.
"""

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
class TestAccountSubscriptionGating:
    def test_no_subscription_returns_none(self, db_session: Session) -> None:
        world = make_world(db_session)
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is None

    def test_active_subscription_returns_subscription(
        self, db_session: Session
    ) -> None:
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

    def test_expired_subscription_returns_none(self, db_session: Session) -> None:
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
            end_date=datetime.now(UTC) - timedelta(days=1),
        )
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is None

    def test_cancelled_subscription_returns_none(self, db_session: Session) -> None:
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.cancelled,
        )
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is None

    def test_trialing_subscription_treated_as_active(self, db_session: Session) -> None:
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.trialing,
        )
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.id == sub.id

    def test_pending_subscription_treated_as_active(self, db_session: Session) -> None:
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.pending,
        )
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.id == sub.id

    def test_full_lifecycle(self, db_session: Session) -> None:
        """No sub -> add active -> returns sub -> cancel -> returns None."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        repo = AccountSubscriptionRepository(db_session)

        # No subscription
        assert repo.get_active_account_subscription(world.account.id) is None

        # Add active subscription
        sub = make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )

        # Returns subscription
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.id == sub.id

        # Cancel it
        repo.update_account_subscription_status(
            sub.external_id, SubscriptionStatus.cancelled
        )

        # Returns None
        result = repo.get_active_account_subscription(world.account.id)
        assert result is None

    def test_subscription_plan_accessible(self, db_session: Session) -> None:
        """Verify plan features are accessible via selectinload relationship."""
        world = make_world(db_session)
        plan = make_subscription_plan(
            db_session,
            features_included=["voice", "sms"],
            features_excluded=["whatsapp"],
        )
        make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.active,
        )
        repo = AccountSubscriptionRepository(db_session)
        result = repo.get_active_account_subscription(world.account.id)
        assert result is not None
        assert result.subscription_plan is not None
        assert "voice" in result.subscription_plan.features_included
        assert "whatsapp" in result.subscription_plan.features_excluded

    def test_subscription_overlap_detection(self, db_session: Session) -> None:
        """Active subscription exists -> overlap returns True."""
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

    def test_no_overlap_with_expired(self, db_session: Session) -> None:
        """Expired subscription -> no overlap."""
        world = make_world(db_session)
        plan = make_subscription_plan(db_session)
        now = datetime.now(UTC)
        make_account_subscription(
            db_session,
            account_id=world.account.id,
            subscription_plan_id=plan.id,
            status=SubscriptionStatus.expired,
            start_date=now - timedelta(days=60),
            end_date=now - timedelta(days=30),
        )
        repo = AccountSubscriptionRepository(db_session)
        has_overlap = repo.check_subscription_overlap(
            world.account.id,
            start_date=now,
            end_date=now + timedelta(days=30),
        )
        assert has_overlap is False

    def test_tenant_isolation(self, db_session: Session) -> None:
        """Account A's subscription is not visible to Account B."""
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
