from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.tos_acceptance import TosAcceptance
from pal_repository.data_classes.tos_acceptance import TosAcceptanceData
from utils.log import logger


def _to_data(row: TosAcceptance) -> TosAcceptanceData:
    """Convert an ORM TosAcceptance to a TosAcceptanceData."""
    return TosAcceptanceData(
        id=row.id,
        account_id=row.account_id,
        display_name=row.display_name,
        tos_version=row.tos_version,
        user_id=row.user_id,
        user_email=row.user_email,
        accepted_at=row.accepted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TosAcceptanceRepository:
    """Async-only repository for TOS acceptance records.

    All methods return ``TosAcceptanceData`` — ORM objects never escape this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        account_id: uuid.UUID,
        display_name: str,
        tos_version: str,
        user_id: uuid.UUID,
        user_email: str,
        accepted_at: datetime,
    ) -> None:
        """Create a new TOS acceptance record.

        Raises:
            IntegrityError: If the (account_id, tos_version) combination already exists.
            SQLAlchemyError: If the insert fails.
        """
        try:
            tos_acceptance = TosAcceptance(
                account_id=account_id,
                display_name=display_name,
                tos_version=tos_version,
                user_id=user_id,
                user_email=user_email,
                accepted_at=accepted_at,
            )
            self.session.add(tos_acceptance)
            await self.session.commit()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating TOS acceptance record: {e}")
            raise

    async def get_by_version(
        self, account_id: uuid.UUID, tos_version: str
    ) -> TosAcceptanceData | None:
        """Retrieve TOS acceptance for a specific version and account."""
        try:
            result = await self.session.execute(
                select(TosAcceptance).filter(
                    TosAcceptance.account_id == account_id,
                    TosAcceptance.tos_version == tos_version,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving TOS acceptance by version: {e}")
            raise

    async def get_latest(self, account_id: uuid.UUID) -> TosAcceptanceData | None:
        """Retrieve the most recent TOS acceptance for an account."""
        try:
            result = await self.session.execute(
                select(TosAcceptance)
                .filter(TosAcceptance.account_id == account_id)
                .order_by(TosAcceptance.accepted_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving latest TOS acceptance: {e}")
            raise
