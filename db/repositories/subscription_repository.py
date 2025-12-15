import uuid
from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from db.tables.subscriptions import (
    AccountSubscription,
    ProjectSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from utils.log import logger


class SubscriptionPlanRepository:
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
                .filter(
                    SubscriptionPlan.id == plan_id, SubscriptionPlan.active.is_(True)
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving subscription plan: {e}")
            return None

    def get_subscription_plans(
        self, hidden: Optional[bool] = None
    ) -> List[SubscriptionPlan]:
        """Get all subscription plans, optionally filtered by hidden status."""
        try:
            query = self.session.query(SubscriptionPlan).filter(
                SubscriptionPlan.active.is_(True)
            )

            # Apply hidden filter if specified
            if hidden is not None:
                query = query.filter(SubscriptionPlan.hidden == hidden)

            return query.order_by(SubscriptionPlan.created_at.desc()).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving subscription plans: {e}")
            return []

    def create_subscription_plan(self, **kwargs) -> SubscriptionPlan:
        """Create a new subscription plan."""
        try:
            plan = SubscriptionPlan(**kwargs)

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
                raise ValueError(f"Subscription plan {plan_id} not found")

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

    def has_active_account_subscriptions(self, plan_id: uuid.UUID) -> bool:
        """Check if a subscription plan has any active (non-deleted) account subscriptions."""
        try:
            active_subscription = (
                self.session.query(AccountSubscription)
                .filter(
                    and_(
                        AccountSubscription.subscription_plan_id == plan_id,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.active,
                            AccountSubscription.status == SubscriptionStatus.pending,
                        ),
                    )
                )
                .first()
            )
            return active_subscription is not None
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error checking for active account subscriptions: {e}")
            return True  # Be conservative and assume there are active subscriptions on error

    def delete_subscription_plan(self, plan_id: uuid.UUID):
        try:
            plan = self.get_subscription_plan_by_id(plan_id)
            if not plan:
                raise ValueError(f"Subscription plan {plan_id} not found")

            self.session.delete(plan)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error expiring/hard deleting subscription plan: {e}")
            raise


class AccountSubscriptionRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def check_subscription_overlap(
        self,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime | None,
    ) -> bool:
        """Check if there's an overlapping active subscription.

        Args:
            account_id: The account ID
            start_date: Start date of the new subscription
            end_date: End date of the new subscription (None means ongoing)

        Returns:
            True if there's an overlap, False otherwise

        Overlap logic:
            - If existing subscription has no end_date (ongoing), it overlaps with any new subscription starting before infinity
            - If new subscription has no end_date (ongoing), it overlaps with any existing subscription not yet ended
            - Otherwise, normal date range overlap checking applies
        """
        try:
            overlap_conditions = []

            if end_date is not None:
                overlap_conditions.append(
                    and_(
                        AccountSubscription.end_date.is_(None),
                        AccountSubscription.start_date <= end_date,
                    )
                )
            else:
                overlap_conditions.append(AccountSubscription.end_date.is_(None))

            if end_date is None:
                overlap_conditions.append(
                    or_(
                        AccountSubscription.end_date.is_(None),
                        AccountSubscription.end_date >= start_date,
                    )
                )

            if end_date is not None:
                overlap_conditions.extend(
                    [
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
                    ]
                )

            overlapping = (
                self.session.query(AccountSubscription)
                .filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.pending,
                            AccountSubscription.status == SubscriptionStatus.active,
                        ),
                        or_(*overlap_conditions),
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
        self, account_subscription: AccountSubscription
    ) -> AccountSubscription:
        """Create a new account subscription."""
        try:
            self.session.add(account_subscription)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(account_subscription)
            return account_subscription
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating account subscription: {e}")
            raise

    def get_account_subscriptions(
        self,
        account_id: uuid.UUID,
    ) -> List[AccountSubscription]:
        """Get all active subscriptions for an account.

        Returns subscriptions that are either:
        - Ongoing (end_date is None)
        - Or haven't ended yet (end_date > now)
        """
        now = datetime.now(UTC)
        try:
            query = (
                self.session.query(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.active,
                            AccountSubscription.status == SubscriptionStatus.pending,
                        ),
                        or_(
                            AccountSubscription.end_date.is_(None),
                            AccountSubscription.end_date > now,
                        ),
                    )
                )
                .order_by(AccountSubscription.start_date)
            )
            return query.all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account subscriptions: {e}")
            return []

    def get_account_subscription(
        self,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> Optional[AccountSubscription]:
        """Get the latest version of an account subscription by external_id."""
        try:
            return (
                self.session.query(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(
                    AccountSubscription.account_id == account_id,
                    AccountSubscription.external_id == external_id,
                )
                .order_by(AccountSubscription.version.desc())
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account subscription by external_id: {e}")
            return None

    def get_account_subscription_by_external_id(
        self, external_id: uuid.UUID
    ) -> Optional[AccountSubscription]:
        """Get the latest version of an account subscription by external_id."""
        try:
            return (
                self.session.query(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(AccountSubscription.external_id == external_id)
                .order_by(AccountSubscription.version.desc())
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving account subscription by external_id: {e}")
            return None

    def update_account_subscription_status(
        self, external_id: uuid.UUID, new_status: SubscriptionStatus
    ) -> Optional[AccountSubscription]:
        """Update only the status of the latest version of an account subscription."""
        try:
            subscription = self.get_account_subscription_by_external_id(external_id)
            if not subscription:
                return None

            subscription.status = new_status
            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(subscription)
            return subscription
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating account subscription status: {e}")
            raise

    def get_active_account_subscription(
        self, account_id: uuid.UUID
    ) -> Optional[AccountSubscription]:
        """Get the active account subscription for an account.

        Returns the most recent subscription that is either ongoing or hasn't ended yet.
        """
        now = datetime.now(UTC)
        try:
            return (
                self.session.query(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.active,
                            AccountSubscription.status == SubscriptionStatus.pending,
                        ),
                        or_(
                            AccountSubscription.end_date.is_(None),
                            AccountSubscription.end_date > now,
                        ),
                    )
                )
                .order_by(AccountSubscription.start_date.desc())
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving active account subscription: {e}")
            return None

    def update_account_subscription(
        self, subscription_id: uuid.UUID, **kwargs
    ) -> Optional[AccountSubscription]:
        """Update account subscription with new fields."""
        try:
            subscription = (
                self.session.query(AccountSubscription)
                .filter(AccountSubscription.id == subscription_id)
                .first()
            )

            if not subscription:
                return None

            for key, value in kwargs.items():
                if hasattr(subscription, key):
                    setattr(subscription, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(subscription)
            return subscription

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating account subscription: {e}")
            raise

    def update_payment_method(
        self, subscription_id: uuid.UUID, payment_method
    ) -> Optional[AccountSubscription]:
        """Update the payment method of an account subscription."""
        try:
            subscription = (
                self.session.query(AccountSubscription)
                .filter(AccountSubscription.id == subscription_id)
                .first()
            )

            if not subscription:
                return None

            subscription.payment_method = payment_method

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(subscription)
            return subscription

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating payment method: {e}")
            raise


class ProjectSubscriptionRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_project_subscription(
        self,
        project_id: uuid.UUID,
        subscription_id: uuid.UUID,
        stripe_product_id: str | None = None,
    ) -> ProjectSubscription:
        """Create a new project subscription."""
        try:
            project_subscription = ProjectSubscription(
                id=uuid.uuid4(),
                project_id=project_id,
                subscription_id=subscription_id,
                stripe_product_id=stripe_product_id,
                deleted=False,
            )

            self.session.add(project_subscription)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(project_subscription)
            return project_subscription
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating project subscription: {e}")
            raise

    def get_project_subscriptions_by_subscription_id(
        self, subscription_id: uuid.UUID
    ) -> List[ProjectSubscription]:
        """Get all project subscriptions for a given subscription ID."""
        try:
            query = self.session.query(ProjectSubscription).filter(
                ProjectSubscription.subscription_id == subscription_id,
                ProjectSubscription.deleted.is_(False),
            )
            return query.all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving project subscriptions: {e}")
            return []

    def get_project_subscription(
        self, project_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> Optional[ProjectSubscription]:
        """Get a specific project subscription by project and subscription IDs."""
        try:
            return (
                self.session.query(ProjectSubscription)
                .filter(
                    ProjectSubscription.project_id == project_id,
                    ProjectSubscription.subscription_id == subscription_id,
                    ProjectSubscription.deleted.is_(False),
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving project subscription: {e}")
            return None

    def delete_project_subscription(
        self, project_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> bool:
        """Soft delete a project subscription by setting deleted flag to True."""
        try:
            project_subscription = self.get_project_subscription(
                project_id, subscription_id
            )
            if not project_subscription:
                return False

            project_subscription.deleted = True

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting project subscription: {e}")
            raise

    def create_project_subscription_with_prices(
        self,
        project_id: uuid.UUID,
        subscription_id: uuid.UUID,
        call_price_id: Optional[str] = None,
        order_price_id: Optional[str] = None,
    ) -> ProjectSubscription:
        """Create a new project subscription with price IDs."""
        try:
            project_subscription = ProjectSubscription(
                id=uuid.uuid4(),
                project_id=project_id,
                subscription_id=subscription_id,
                call_price_id=call_price_id,
                order_price_id=order_price_id,
                deleted=False,
            )

            self.session.add(project_subscription)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(project_subscription)
            return project_subscription
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating project subscription with prices: {e}")
            raise

    def get_project_subscription_by_project_id(
        self, project_id: uuid.UUID
    ) -> Optional[ProjectSubscription]:
        """Get project subscription by project ID."""
        try:
            return (
                self.session.query(ProjectSubscription)
                .filter(
                    ProjectSubscription.project_id == project_id,
                    ProjectSubscription.deleted.is_(False),
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving project subscription by project ID: {e}")
            return None

    def update_project_subscription(
        self, id: uuid.UUID, **kwargs
    ) -> Optional[ProjectSubscription]:
        """Update project subscription with new fields."""
        try:
            subscription = (
                self.session.query(ProjectSubscription)
                .filter(ProjectSubscription.id == id)
                .first()
            )

            if not subscription:
                return None

            for key, value in kwargs.items():
                if hasattr(subscription, key):
                    setattr(subscription, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(subscription)
            return subscription

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating project subscription: {e}")
            raise


class AsyncAccountSubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_account_subscription(
        self, account_id: uuid.UUID, external_id: uuid.UUID
    ) -> Optional[AccountSubscription]:
        """Get the latest version of an account subscription by external_id."""
        try:
            query = (
                select(AccountSubscription)
                .filter(AccountSubscription.account_id == account_id)
                .filter(AccountSubscription.external_id == external_id)
                .order_by(AccountSubscription.version.desc())
                .limit(1)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving account subscription by external_id: {e}",
                extra={
                    "account_id": account_id,
                    "external_id": external_id,
                },
            )
            return None
