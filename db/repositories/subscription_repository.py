import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables.subscriptions import (
    AccountSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionType,
)
from db.tables.types import TargetTier
from utils.log import logger


class PlanNotFoundError(Exception):
    """Raised when a subscription plan is not found."""

    pass


class SubscriptionRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_subscription_plan_by_id(
        self, plan_id: uuid.UUID
    ) -> Optional[SubscriptionPlan]:
        """Get a subscription plan by ID."""
        try:
            return (
                self.session.query(SubscriptionPlan)
                .filter(SubscriptionPlan.id == plan_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving subscription plan: {e}")
            return None

    def get_subscription_plans(self) -> List[SubscriptionPlan]:
        """Get all subscription plans."""
        try:
            return (
                self.session.query(SubscriptionPlan)
                .order_by(SubscriptionPlan.created_at.desc())
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving subscription plans: {e}")
            return []

    def create_subscription_plan(
        self, name: str, tier: TargetTier, **kwargs
    ) -> SubscriptionPlan:
        """Create a new subscription plan."""
        try:
            plan = SubscriptionPlan(id=uuid.uuid4(), name=name, tier=tier)

            for key, value in kwargs.items():
                if value is not None and hasattr(plan, key):
                    setattr(plan, key, value)

            if not hasattr(plan, "features_included") or plan.features_included is None:
                plan.features_included = []
            if not hasattr(plan, "features_excluded") or plan.features_excluded is None:
                plan.features_excluded = []

            self.session.add(plan)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(plan)
            return plan
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating subscription plan: {e}")
            raise

    def update_subscription_plan(
        self, plan_id: uuid.UUID, **kwargs
    ) -> SubscriptionPlan | None:
        """Update a subscription plan."""
        try:
            plan = self.get_subscription_plan_by_id(plan_id)
            if not plan:
                raise PlanNotFoundError(f"Subscription plan {plan_id} not found")

            for key, value in kwargs.items():
                if value is not None and hasattr(plan, key):
                    setattr(plan, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(plan)
            return plan
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating subscription plan: {e}")
            raise

    def delete_subscription_plan(self, plan_id: uuid.UUID) -> None:
        """Delete a subscription plan."""
        try:
            plan = self.get_subscription_plan_by_id(plan_id)
            if not plan:
                raise PlanNotFoundError(f"Subscription plan {plan_id} not found")
            self.session.delete(plan)
            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting subscription plan: {e}")
            raise

    def get_last_trial_subscription(
        self, account_id: uuid.UUID
    ) -> Optional[AccountSubscription]:
        """Get the last trial subscription for an account."""
        try:
            return (
                self.session.query(AccountSubscription)
                .filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        AccountSubscription.subscription_type == SubscriptionType.trial,
                    )
                )
                .order_by(AccountSubscription.end_date.desc())
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving last trial subscription: {e}")
            return None

    def check_subscription_overlap(
        self,
        account_id: uuid.UUID,
        subscription_type: SubscriptionType,
        start_date: datetime,
        end_date: datetime,
    ) -> bool:
        """Check if there's an overlapping active subscription of the same type."""
        try:
            overlapping = (
                self.session.query(AccountSubscription)
                .filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        AccountSubscription.subscription_type == subscription_type,
                        AccountSubscription.status == SubscriptionStatus.active,
                        or_(
                            and_(
                                AccountSubscription.start_date <= start_date,
                                AccountSubscription.end_date >= start_date,
                            ),
                            and_(
                                AccountSubscription.start_date <= end_date,
                                AccountSubscription.end_date >= end_date,
                            ),
                            and_(
                                start_date <= AccountSubscription.start_date,
                                end_date >= AccountSubscription.end_date,
                            ),
                        ),
                    )
                )
                .first()
            )
            return overlapping is not None
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error checking subscription overlap: {e}")
            return True

    def create_account_subscription(
        self,
        account_id: uuid.UUID,
        subscription_plan_id: uuid.UUID,
        subscription_type: SubscriptionType,
        start_date: datetime,
        end_date: datetime,
        **kwargs,
    ) -> AccountSubscription:
        """Create a new account subscription."""
        try:
            subscription = AccountSubscription(
                external_id=uuid.uuid4(),
                account_id=account_id,
                subscription_plan_id=subscription_plan_id,
                subscription_type=subscription_type,
                start_date=start_date,
                end_date=end_date,
                status=SubscriptionStatus.active,
            )

            for key, value in kwargs.items():
                if value is not None and hasattr(subscription, key):
                    setattr(subscription, key, value)

            self.session.add(subscription)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(subscription)
            return subscription
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating account subscription: {e}")
            raise
