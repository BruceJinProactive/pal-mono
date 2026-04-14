from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.subscription_plan import SubscriptionPlanData
from db.tables.subscriptions import AccountSubscription, SubscriptionPlan
from db.tables.types import SubscriptionStatus, TargetTier
from utils.log import logger


def _to_data(row: SubscriptionPlan) -> SubscriptionPlanData:
    """Convert an ORM SubscriptionPlan to a SubscriptionPlanData.

    Enum fields are converted to their string values so the record does not
    expose ``db.tables.types`` to consumers.
    """
    return SubscriptionPlanData(
        id=row.id,
        name=row.name,
        description=row.description,
        tier=row.tier.value if row.tier else "",
        features_included=list(row.features_included) if row.features_included else [],
        features_excluded=list(row.features_excluded) if row.features_excluded else [],
        call_quota=row.call_quota,
        order_quota=row.order_quota,
        call_overage_charge=row.call_overage_charge,
        order_overage_charge=row.order_overage_charge,
        free_trial_days=row.free_trial_days,
        credit_amount=row.credit_amount,
        monthly_fee=row.monthly_fee,
        active=row.active,
        sort_id=row.sort_id,
        hidden=bool(row.hidden),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SubscriptionPlanRepository:
    """Async-only repository for SubscriptionPlan records.

    All methods return ``SubscriptionPlanData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, plan_id: uuid.UUID) -> SubscriptionPlanData | None:
        """Retrieve a single active subscription plan by primary key."""
        try:
            result = await self.session.execute(
                select(SubscriptionPlan).filter(
                    SubscriptionPlan.id == plan_id,
                    SubscriptionPlan.active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving subscription plan by ID: {e}")
            raise

    async def get_all(self, hidden: bool | None = None) -> list[SubscriptionPlanData]:
        """List all active subscription plans, optionally filtered by hidden status."""
        try:
            query = select(SubscriptionPlan).filter(SubscriptionPlan.active.is_(True))
            if hidden is not None:
                query = query.filter(SubscriptionPlan.hidden == hidden)
            query = query.order_by(SubscriptionPlan.created_at.desc())

            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error listing subscription plans: {e}")
            raise

    async def has_active_account_subscriptions(self, plan_id: uuid.UUID) -> bool:
        """Check if a plan has any active or pending account subscriptions.

        Conservative: returns ``True`` on DB error to prevent accidental
        deletion of plans that may still be in use.
        """
        try:
            result = await self.session.execute(
                select(AccountSubscription).filter(
                    and_(
                        AccountSubscription.subscription_plan_id == plan_id,
                        or_(
                            AccountSubscription.status == SubscriptionStatus.active,
                            AccountSubscription.status == SubscriptionStatus.pending,
                        ),
                    )
                )
            )
            row = result.scalars().first()
            return row is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking for active account subscriptions: {e}")
            return True

    async def create(self, record: SubscriptionPlanData) -> None:
        """Create a new subscription plan.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = SubscriptionPlan(
                id=record.id,
                name=record.name,
                description=record.description,
                tier=TargetTier(record.tier),
                features_included=record.features_included or [],
                features_excluded=record.features_excluded or [],
                call_quota=record.call_quota,
                order_quota=record.order_quota,
                call_overage_charge=record.call_overage_charge,
                order_overage_charge=record.order_overage_charge,
                free_trial_days=record.free_trial_days,
                credit_amount=record.credit_amount,
                monthly_fee=record.monthly_fee,
                active=record.active,
                sort_id=record.sort_id,
                hidden=record.hidden,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating subscription plan: {e}")
            raise

    async def update(
        self, plan_id: uuid.UUID, record: SubscriptionPlanData
    ) -> SubscriptionPlanData | None:
        """Update an existing subscription plan.

        Fields from *record* that are non-None overwrite the existing values.

        Raises:
            ValueError: If the plan is not found.
            SQLAlchemyError: If the update fails.
        """
        try:
            result = await self.session.execute(
                select(SubscriptionPlan).filter(
                    SubscriptionPlan.id == plan_id,
                    SubscriptionPlan.active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                raise ValueError(f"Subscription plan {plan_id} not found")

            if record.name is not None:
                row.name = record.name
            if record.description is not None:
                row.description = record.description
            if record.tier is not None:
                row.tier = TargetTier(record.tier)
            if record.features_included is not None:
                row.features_included = record.features_included
            if record.features_excluded is not None:
                row.features_excluded = record.features_excluded
            if record.call_quota is not None:
                row.call_quota = record.call_quota
            if record.order_quota is not None:
                row.order_quota = record.order_quota
            if record.call_overage_charge is not None:
                row.call_overage_charge = record.call_overage_charge
            if record.order_overage_charge is not None:
                row.order_overage_charge = record.order_overage_charge
            if record.free_trial_days is not None:
                row.free_trial_days = record.free_trial_days
            if record.credit_amount is not None:
                row.credit_amount = record.credit_amount
            if record.monthly_fee is not None:
                row.monthly_fee = record.monthly_fee
            if record.sort_id is not None:
                row.sort_id = record.sort_id
            if record.active is not None:
                row.active = record.active
            if record.hidden is not None:
                setattr(row, "hidden", record.hidden)

            data = _to_data(row)
            await self.session.commit()
            return data
        except ValueError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating subscription plan: {e}")
            raise

    async def delete(self, plan_id: uuid.UUID) -> None:
        """Hard-delete a subscription plan.

        Raises:
            ValueError: If the plan is not found.
            SQLAlchemyError: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(SubscriptionPlan).filter(
                    SubscriptionPlan.id == plan_id,
                    SubscriptionPlan.active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                raise ValueError(f"Subscription plan {plan_id} not found")

            await self.session.delete(row)
            await self.session.commit()
        except ValueError:
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting subscription plan: {e}")
            raise
