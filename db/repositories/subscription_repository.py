import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from db.tables.subscriptions import (
    AccountSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionType,
)
from db.tables.types import TargetTier
from utils.log import logger


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
        self,
        name: str,
        tier: TargetTier,
        description: Optional[str] = None,
        features_included: Optional[List[str]] = None,
        features_excluded: Optional[List[str]] = None,
        call_quota: Optional[int] = None,
        order_quota: Optional[int] = None,
        call_overage_charge: Optional[int] = None,
        order_overage_charge: Optional[int] = None,
        free_trial_days: Optional[int] = None,
        monthly_fee: Optional[int] = None,
        stripe_price_id: Optional[str] = None,
        active: bool = True,
        sort_id: Optional[int] = None,
    ) -> SubscriptionPlan:
        """Create a new subscription plan."""
        try:
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=name,
                description=description,
                tier=tier,
                features_included=features_included or [],
                features_excluded=features_excluded or [],
                call_quota=call_quota,
                order_quota=order_quota,
                call_overage_charge=call_overage_charge,
                order_overage_charge=order_overage_charge,
                free_trial_days=free_trial_days,
                monthly_fee=monthly_fee,
                stripe_price_id=stripe_price_id,
                active=active,
                sort_id=sort_id,
            )

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
        call_quota: Optional[int] = None,
        order_quota: Optional[int] = None,
        call_overage_charge: Optional[int] = None,
        order_overage_charge: Optional[int] = None,
        monthly_fee: Optional[int] = None,
        stripe_subscription_id: Optional[str] = None,
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
                call_quota=call_quota,
                order_quota=order_quota,
                call_overage_charge=call_overage_charge,
                order_overage_charge=order_overage_charge,
                monthly_fee=monthly_fee,
                stripe_subscription_id=stripe_subscription_id,
                status=SubscriptionStatus.active,
            )

            self.session.add(subscription)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            subscription = (
                self.session.query(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(AccountSubscription.id == subscription.id)
                .first()
            )

            return subscription
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating account subscription: {e}")
            raise
