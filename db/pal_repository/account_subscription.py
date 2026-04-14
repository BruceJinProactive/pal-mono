from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.pal_repository.data_classes.account_subscription import AccountSubscriptionData
from db.pal_repository.subscription_plan import _to_data as _plan_to_data
from db.tables.subscriptions import AccountSubscription
from db.tables.types import PaymentMethod, RecurringCreditFrequency, SubscriptionStatus
from utils.log import logger

# Enum fields that require conversion from string values in **kwargs updates.
_ENUM_FIELDS: dict[str, type] = {
    "status": SubscriptionStatus,
    "payment_method": PaymentMethod,
    "recurring_credit_frequency": RecurringCreditFrequency,
}


def _to_data(row: AccountSubscription) -> AccountSubscriptionData:
    """Convert an ORM AccountSubscription to an AccountSubscriptionData.

    Does not include the subscription_plan relationship.
    """
    return AccountSubscriptionData(
        id=row.id,
        external_id=row.external_id,
        version=row.version,
        account_id=row.account_id,
        subscription_plan_id=row.subscription_plan_id,
        stripe_product_id=row.stripe_product_id,
        payment_method=row.payment_method.value if row.payment_method else "",
        trial_start_date=row.trial_start_date,
        start_date=row.start_date,
        end_date=row.end_date,
        stripe_subscription_id=row.stripe_subscription_id,
        status=row.status.value if row.status else "",
        recurring_credit_enabled=row.recurring_credit_enabled,
        recurring_credit_amount=row.recurring_credit_amount,
        recurring_credit_frequency=(
            row.recurring_credit_frequency.value
            if row.recurring_credit_frequency
            else None
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        subscription_plan=None,
    )


def _to_data_with_plan(row: AccountSubscription) -> AccountSubscriptionData:
    """Convert an ORM AccountSubscription with eagerly-loaded subscription_plan."""
    plan_data = _plan_to_data(row.subscription_plan) if row.subscription_plan else None
    return AccountSubscriptionData(
        id=row.id,
        external_id=row.external_id,
        version=row.version,
        account_id=row.account_id,
        subscription_plan_id=row.subscription_plan_id,
        stripe_product_id=row.stripe_product_id,
        payment_method=row.payment_method.value if row.payment_method else "",
        trial_start_date=row.trial_start_date,
        start_date=row.start_date,
        end_date=row.end_date,
        stripe_subscription_id=row.stripe_subscription_id,
        status=row.status.value if row.status else "",
        recurring_credit_enabled=row.recurring_credit_enabled,
        recurring_credit_amount=row.recurring_credit_amount,
        recurring_credit_frequency=(
            row.recurring_credit_frequency.value
            if row.recurring_credit_frequency
            else None
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        subscription_plan=plan_data,
    )


class AccountSubscriptionRepository:
    """Async-only repository for AccountSubscription records.

    All methods return ``AccountSubscriptionData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_subscription_overlap(
        self,
        account_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime | None,
    ) -> bool:
        """Check if there is an overlapping active subscription.

        Conservative: returns ``True`` on DB error to prevent double-billing.
        """
        try:
            overlap_conditions: list = []

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

            result = await self.session.execute(
                select(AccountSubscription).filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.pending,
                            AccountSubscription.status == SubscriptionStatus.active,
                            AccountSubscription.status == SubscriptionStatus.trialing,
                        ),
                        or_(*overlap_conditions),
                    )
                )
            )
            row = result.scalars().first()
            return row is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking subscription overlap: {e}")
            return True

    async def get_account_subscriptions(
        self, account_id: uuid.UUID
    ) -> list[AccountSubscriptionData]:
        """Get all active/pending subscriptions for an account.

        Returns subscriptions that are ongoing or haven't ended yet.
        Uses selectinload for the subscription_plan relationship.
        """
        now = datetime.now(UTC)
        try:
            result = await self.session.execute(
                select(AccountSubscription)
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
            rows = result.scalars().all()
            return [_to_data_with_plan(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving account subscriptions: {e}")
            raise

    async def get_by_account_and_external_id(
        self, account_id: uuid.UUID, external_id: uuid.UUID
    ) -> AccountSubscriptionData | None:
        """Get the latest version of an account subscription by external_id."""
        try:
            result = await self.session.execute(
                select(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(
                    AccountSubscription.account_id == account_id,
                    AccountSubscription.external_id == external_id,
                )
                .order_by(AccountSubscription.version.desc())
            )
            row = result.scalars().first()
            return _to_data_with_plan(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving account subscription by external_id: {e}")
            raise

    async def get_by_external_id(
        self, external_id: uuid.UUID
    ) -> AccountSubscriptionData | None:
        """Get the latest version of an account subscription by external_id."""
        try:
            result = await self.session.execute(
                select(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(AccountSubscription.external_id == external_id)
                .order_by(AccountSubscription.version.desc())
            )
            row = result.scalars().first()
            return _to_data_with_plan(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving account subscription by external_id: {e}")
            raise

    async def get_by_stripe_subscription_id(
        self, stripe_subscription_id: str
    ) -> AccountSubscriptionData | None:
        """Get an account subscription by Stripe subscription ID."""
        try:
            result = await self.session.execute(
                select(AccountSubscription)
                .filter(
                    AccountSubscription.stripe_subscription_id == stripe_subscription_id
                )
                .order_by(AccountSubscription.version.desc())
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving account subscription by stripe_subscription_id: {e}"
            )
            raise

    async def get_active(self, account_id: uuid.UUID) -> AccountSubscriptionData | None:
        """Get the most recent valid subscription for an account."""
        now = datetime.now(UTC)
        try:
            result = await self.session.execute(
                select(AccountSubscription)
                .options(selectinload(AccountSubscription.subscription_plan))
                .filter(
                    and_(
                        AccountSubscription.account_id == account_id,
                        AccountSubscription.start_date <= now,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.active,
                            AccountSubscription.status == SubscriptionStatus.pending,
                            AccountSubscription.status == SubscriptionStatus.trialing,
                        ),
                        or_(
                            AccountSubscription.end_date.is_(None),
                            AccountSubscription.end_date > now,
                        ),
                    )
                )
                .order_by(AccountSubscription.start_date.desc())
            )
            row = result.scalars().first()
            return _to_data_with_plan(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving active account subscription: {e}")
            raise

    async def get_with_stripe_id(
        self, account_id: uuid.UUID
    ) -> list[AccountSubscriptionData]:
        """Get all account subscriptions that have a stripe_subscription_id."""
        try:
            result = await self.session.execute(
                select(AccountSubscription)
                .filter(
                    AccountSubscription.account_id == account_id,
                    AccountSubscription.stripe_subscription_id.isnot(None),
                )
                .order_by(AccountSubscription.created_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving account subscriptions with stripe_id: {e}")
            raise

    async def create(self, record: AccountSubscriptionData) -> None:
        """Create a new account subscription.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = AccountSubscription(
                id=record.id,
                external_id=record.external_id,
                version=record.version,
                account_id=record.account_id,
                subscription_plan_id=record.subscription_plan_id,
                stripe_product_id=record.stripe_product_id,
                payment_method=PaymentMethod(record.payment_method),
                trial_start_date=record.trial_start_date,
                start_date=record.start_date,
                end_date=record.end_date,
                stripe_subscription_id=record.stripe_subscription_id,
                status=SubscriptionStatus(record.status),
                recurring_credit_enabled=record.recurring_credit_enabled,
                recurring_credit_amount=record.recurring_credit_amount,
                recurring_credit_frequency=(
                    RecurringCreditFrequency(record.recurring_credit_frequency)
                    if record.recurring_credit_frequency
                    else None
                ),
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating account subscription: {e}")
            raise

    async def update_status(
        self, external_id: uuid.UUID, new_status: str
    ) -> AccountSubscriptionData | None:
        """Update the status of the latest version of an account subscription.

        Returns the updated record, or None if not found.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        try:
            result = await self.session.execute(
                select(AccountSubscription)
                .filter(AccountSubscription.external_id == external_id)
                .order_by(AccountSubscription.version.desc())
            )
            row = result.scalars().first()
            if not row:
                return None

            row.status = SubscriptionStatus(new_status)
            data = _to_data(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating account subscription status: {e}")
            raise

    async def update(
        self, subscription_id: uuid.UUID, **kwargs: object
    ) -> AccountSubscriptionData | None:
        """Update an account subscription with arbitrary fields.

        Known enum field keys (``status``, ``payment_method``,
        ``recurring_credit_frequency``) are automatically converted from
        string values to the corresponding enum type.

        Returns the updated record, or None if not found.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        try:
            result = await self.session.execute(
                select(AccountSubscription).filter(
                    AccountSubscription.id == subscription_id
                )
            )
            row = result.scalars().first()
            if not row:
                return None

            for key, value in kwargs.items():
                if hasattr(row, key):
                    if key in _ENUM_FIELDS and value is not None:
                        value = _ENUM_FIELDS[key](value)
                    setattr(row, key, value)

            data = _to_data(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating account subscription: {e}")
            raise

    async def update_payment_method(
        self, subscription_id: uuid.UUID, payment_method: str
    ) -> AccountSubscriptionData | None:
        """Update the payment method of an account subscription.

        Returns the updated record, or None if not found.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        try:
            result = await self.session.execute(
                select(AccountSubscription).filter(
                    AccountSubscription.id == subscription_id
                )
            )
            row = result.scalars().first()
            if not row:
                return None

            row.payment_method = PaymentMethod(payment_method)
            data = _to_data(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating payment method: {e}")
            raise
