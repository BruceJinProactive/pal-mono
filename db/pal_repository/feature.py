from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.feature import FeatureData
from db.tables.features import Feature
from db.tables.types import IdentifierType
from utils.log import logger


def _to_data(row: Feature) -> FeatureData:
    """Convert an ORM Feature to a FeatureData."""
    return FeatureData(
        id=row.id,
        feature=row.feature,
        identifier_type=row.identifier_type.value,
        identifier=row.identifier,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class FeatureRepository:
    """Async-only repository for Feature records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_enablement(
        self, feature: str, identifier_type: str, identifier: str
    ) -> bool:
        """Check if a feature is enabled for a specific identifier."""
        try:
            result = await self.session.execute(
                select(Feature.enabled).where(
                    Feature.feature == feature,
                    Feature.identifier_type == IdentifierType(identifier_type),
                    Feature.identifier == identifier,
                )
            )
            enabled = result.scalar_one_or_none()
            return enabled if enabled is not None else False
        except Exception:
            await self.session.rollback()
            logger.exception("Error checking feature enablement")
            raise

    async def upsert(
        self, feature: str, identifier_type: str, identifier: str, enabled: bool
    ) -> FeatureData:
        """Create or update a feature flag entry (atomic)."""
        try:
            id_type = IdentifierType(identifier_type)
            stmt = pg_insert(Feature).values(
                id=uuid.uuid4(),
                feature=feature,
                identifier_type=id_type,
                identifier=identifier,
                enabled=enabled,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_feature_identifier",
                set_={"enabled": enabled, "updated_at": func.now()},
            ).returning(Feature)
            result = await self.session.execute(stmt)
            row = result.scalar_one()
            data = _to_data(row)
            await self.session.commit()
            return data
        except Exception:
            await self.session.rollback()
            logger.exception("Error upserting feature")
            raise
