from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.account import AccountData
from db.tables.accounts import Account, AccountStatus
from utils.log import logger


def _to_data(row: Account) -> AccountData:
    """Convert an ORM Account to an AccountData."""
    if row.status is None or row.onboarding_method is None:
        raise ValueError(
            f"Account {row.id} has null required enum fields: "
            f"status={row.status}, onboarding_method={row.onboarding_method}"
        )

    return AccountData(
        id=row.id,
        name=row.name,
        status=row.status.value,
        onboarding_method=row.onboarding_method.value,
        contract_signed=row.contract_signed,
        created_at=row.created_at,
        display_name=row.display_name,
        icon_uri=row.icon_uri,
        industry=row.industry,
        business_description=row.business_description,
        business_faq=row.business_faq,
        business_promotions=row.business_promotions,
        business_catalog=row.business_catalog,
        business_others=row.business_others,
        stripe_customer_id=row.stripe_customer_id,
        stripe_coupon_id=row.stripe_coupon_id,
        current_subscription_id=row.current_subscription_id,
        owner=row.owner,
        segment=row.segment.value if row.segment else None,
        tier=row.tier.value if row.tier else None,
        notes=row.notes,
        phone_number=row.phone_number,
        channels=tuple(row.channels) if row.channels else (),
        notification_preferences=(
            dict(row.notification_preferences) if row.notification_preferences else {}
        ),
        notification_email=row.notification_email,
        updated_at=row.updated_at,
    )


class AccountRepository:
    """Async-only repository for Account records.

    All methods return ``AccountData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, account_id: uuid.UUID) -> AccountData | None:
        """Retrieve an account by its primary key (excludes deleted)."""
        try:
            result = await self.session.execute(
                select(Account)
                .filter(Account.id == account_id)
                .filter(Account.status != AccountStatus.deleted)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving account by ID")
            raise

    async def get_by_name(self, account_name: str) -> AccountData | None:
        """Retrieve an account by name (excludes deleted)."""
        try:
            result = await self.session.execute(
                select(Account)
                .filter(Account.name == account_name)
                .filter(Account.status != AccountStatus.deleted)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving account by name")
            raise

    async def get_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> AccountData | None:
        """Retrieve an account by Stripe customer ID (excludes deleted)."""
        try:
            result = await self.session.execute(
                select(Account)
                .filter(Account.stripe_customer_id == stripe_customer_id)
                .filter(Account.status != AccountStatus.deleted)
                .limit(2)
            )
            rows = result.scalars().all()
            if len(rows) > 1:
                raise ValueError(
                    f"Multiple accounts found for stripe_customer_id={stripe_customer_id}"
                )
            row = rows[0] if rows else None
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving account by Stripe customer ID")
            raise

    async def get_all_account_names(self) -> list[tuple[str, str | None]]:
        """Retrieve all active account names with display names, sorted alphabetically."""
        try:
            result = await self.session.execute(
                select(Account.name, Account.display_name)
                .filter(Account.status != AccountStatus.deleted)
                .order_by(Account.name)
            )
            return list(result.tuples().all())
        except Exception:
            logger.exception("Error retrieving account names")
            raise
