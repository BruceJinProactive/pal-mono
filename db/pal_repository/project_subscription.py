from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.project_subscription import ProjectSubscriptionData
from db.tables.subscriptions import ProjectSubscription
from db.tables.types import PaymentMethod, RecurringCreditFrequency, SubscriptionStatus
from utils.log import logger

# Enum fields that require conversion from string values in **kwargs updates.
_ENUM_FIELDS: dict[str, type] = {
    "status": SubscriptionStatus,
    "payment_method": PaymentMethod,
    "recurring_credit_frequency": RecurringCreditFrequency,
}


def _to_data(row: ProjectSubscription) -> ProjectSubscriptionData:
    """Convert an ORM ProjectSubscription to a ProjectSubscriptionData.

    Enum fields are converted to their string values so the record does not
    expose ``db.tables.types`` to consumers.
    """
    return ProjectSubscriptionData(
        id=row.id,
        external_id=row.external_id,
        version=row.version,
        project_id=row.project_id,
        subscription_id=row.subscription_id,
        subscription_plan_id=row.subscription_plan_id,
        stripe_product_id=row.stripe_product_id,
        stripe_subscription_id=row.stripe_subscription_id,
        payment_method=row.payment_method.value if row.payment_method else None,
        base_price_id=row.base_price_id,
        call_price_id=row.call_price_id,
        order_price_id=row.order_price_id,
        trial_start_date=row.trial_start_date,
        start_date=row.start_date,
        end_date=row.end_date,
        status=row.status.value if row.status else None,
        deleted=row.deleted,
        recurring_credit_enabled=row.recurring_credit_enabled,
        recurring_credit_amount=row.recurring_credit_amount,
        recurring_credit_frequency=(
            row.recurring_credit_frequency.value
            if row.recurring_credit_frequency
            else None
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProjectSubscriptionRepository:
    """Async-only repository for ProjectSubscription records.

    All methods return ``ProjectSubscriptionData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_subscription_id(
        self, subscription_id: uuid.UUID
    ) -> list[ProjectSubscriptionData]:
        """Get all non-deleted project subscriptions for a given subscription ID."""
        try:
            result = await self.session.execute(
                select(ProjectSubscription).filter(
                    ProjectSubscription.subscription_id == subscription_id,
                    ProjectSubscription.deleted.is_(False),
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project subscriptions: {e}")
            raise

    async def get(
        self, project_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> ProjectSubscriptionData | None:
        """Get a specific non-deleted project subscription."""
        try:
            result = await self.session.execute(
                select(ProjectSubscription).filter(
                    ProjectSubscription.project_id == project_id,
                    ProjectSubscription.subscription_id == subscription_id,
                    ProjectSubscription.deleted.is_(False),
                )
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project subscription: {e}")
            raise

    async def get_by_project_id(
        self, project_id: uuid.UUID
    ) -> ProjectSubscriptionData | None:
        """Get the first non-deleted project subscription for a project."""
        try:
            result = await self.session.execute(
                select(ProjectSubscription)
                .filter(
                    ProjectSubscription.project_id == project_id,
                    ProjectSubscription.deleted.is_(False),
                )
                .order_by(ProjectSubscription.created_at.desc())
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project subscription by project ID: {e}")
            raise

    async def get_by_external_id(
        self, external_id: uuid.UUID
    ) -> ProjectSubscriptionData | None:
        """Get the latest version of a non-deleted project subscription by external_id."""
        try:
            result = await self.session.execute(
                select(ProjectSubscription)
                .filter(
                    ProjectSubscription.external_id == external_id,
                    ProjectSubscription.deleted.is_(False),
                )
                .order_by(ProjectSubscription.version.desc())
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project subscription by external_id: {e}")
            raise

    async def get_active(self, project_id: uuid.UUID) -> ProjectSubscriptionData | None:
        """Get the most recent valid subscription for a project."""
        now = datetime.now(UTC)
        try:
            result = await self.session.execute(
                select(ProjectSubscription)
                .filter(
                    and_(
                        ProjectSubscription.project_id == project_id,
                        ProjectSubscription.deleted.is_(False),
                        or_(
                            ProjectSubscription.status == SubscriptionStatus.active,
                            ProjectSubscription.status == SubscriptionStatus.pending,
                            ProjectSubscription.status == SubscriptionStatus.trialing,
                        ),
                        or_(
                            ProjectSubscription.end_date.is_(None),
                            ProjectSubscription.end_date > now,
                        ),
                    )
                )
                .order_by(ProjectSubscription.start_date.desc())
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving active project subscription: {e}")
            raise

    async def check_subscription_overlap(
        self,
        project_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime | None,
    ) -> bool:
        """Check if there is an overlapping active subscription for a project.

        Conservative: returns ``True`` on DB error to prevent double-billing.
        """
        try:
            overlap_conditions: list = []

            if end_date is not None:
                overlap_conditions.append(
                    and_(
                        ProjectSubscription.end_date.is_(None),
                        ProjectSubscription.start_date <= end_date,
                    )
                )
            else:
                overlap_conditions.append(ProjectSubscription.end_date.is_(None))

            if end_date is None:
                overlap_conditions.append(
                    or_(
                        ProjectSubscription.end_date.is_(None),
                        ProjectSubscription.end_date >= start_date,
                    )
                )

            if end_date is not None:
                overlap_conditions.extend(
                    [
                        and_(
                            ProjectSubscription.start_date <= start_date,
                            ProjectSubscription.end_date >= start_date,
                        ),
                        and_(
                            ProjectSubscription.start_date <= end_date,
                            ProjectSubscription.end_date >= end_date,
                        ),
                        and_(
                            start_date <= ProjectSubscription.start_date,
                            end_date >= ProjectSubscription.end_date,
                        ),
                    ]
                )

            result = await self.session.execute(
                select(ProjectSubscription).filter(
                    and_(
                        ProjectSubscription.project_id == project_id,
                        ProjectSubscription.deleted.is_(False),
                        or_(
                            ProjectSubscription.status == SubscriptionStatus.pending,
                            ProjectSubscription.status == SubscriptionStatus.active,
                            ProjectSubscription.status == SubscriptionStatus.trialing,
                        ),
                        or_(*overlap_conditions),
                    )
                )
            )
            row = result.scalars().first()
            return row is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking project subscription overlap: {e}")
            return True

    async def get_by_stripe_id(
        self, stripe_subscription_id: str
    ) -> ProjectSubscriptionData | None:
        """Get a non-deleted project subscription by Stripe subscription ID.

        Returns the latest version.
        """
        try:
            result = await self.session.execute(
                select(ProjectSubscription)
                .filter(
                    ProjectSubscription.stripe_subscription_id
                    == stripe_subscription_id,
                    ProjectSubscription.deleted.is_(False),
                )
                .order_by(ProjectSubscription.version.desc())
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving project subscription by stripe_subscription_id: {e}"
            )
            raise

    async def create(
        self,
        project_id: uuid.UUID,
        subscription_id: uuid.UUID,
        stripe_product_id: Optional[str] = None,
    ) -> None:
        """Create a new project subscription.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = ProjectSubscription(
                id=uuid.uuid4(),
                project_id=project_id,
                subscription_id=subscription_id,
                stripe_product_id=stripe_product_id,
                deleted=False,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating project subscription: {e}")
            raise

    async def create_with_prices(
        self,
        project_id: uuid.UUID,
        subscription_id: uuid.UUID,
        call_price_id: Optional[str] = None,
        order_price_id: Optional[str] = None,
    ) -> None:
        """Create a new project subscription with price IDs.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = ProjectSubscription(
                id=uuid.uuid4(),
                project_id=project_id,
                subscription_id=subscription_id,
                call_price_id=call_price_id,
                order_price_id=order_price_id,
                deleted=False,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating project subscription with prices: {e}")
            raise

    async def soft_delete(
        self, project_id: uuid.UUID, subscription_id: uuid.UUID
    ) -> bool:
        """Soft-delete a project subscription by setting the deleted flag.

        Returns True if deleted, False if not found.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(ProjectSubscription).filter(
                    ProjectSubscription.project_id == project_id,
                    ProjectSubscription.subscription_id == subscription_id,
                    ProjectSubscription.deleted.is_(False),
                )
            )
            row = result.scalars().first()
            if not row:
                return False

            row.deleted = True
            await self.session.commit()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error soft-deleting project subscription: {e}")
            raise

    async def update(
        self, subscription_id: uuid.UUID, **kwargs: object
    ) -> ProjectSubscriptionData | None:
        """Update a project subscription with arbitrary fields.

        Known enum field keys (``status``, ``payment_method``,
        ``recurring_credit_frequency``) are automatically converted from
        string values to the corresponding enum type.

        Returns the updated record, or None if not found.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        try:
            result = await self.session.execute(
                select(ProjectSubscription).filter(
                    ProjectSubscription.id == subscription_id
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
            logger.error(f"Error updating project subscription: {e}")
            raise

    async def update_status(
        self, external_id: uuid.UUID, new_status: str
    ) -> ProjectSubscriptionData | None:
        """Update the status of the latest version of a project subscription.

        Returns the updated record, or None if not found.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        try:
            result = await self.session.execute(
                select(ProjectSubscription)
                .filter(
                    ProjectSubscription.external_id == external_id,
                    ProjectSubscription.deleted.is_(False),
                )
                .order_by(ProjectSubscription.version.desc())
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
            logger.error(f"Error updating project subscription status: {e}")
            raise
