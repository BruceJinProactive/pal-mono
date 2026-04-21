from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.integration import IntegrationData
from db.tables.integration import Integration, ProjectIntegration
from db.tables.types import IntegrationType
from utils.log import logger


def _to_data(row: Integration) -> IntegrationData:
    """Convert an ORM Integration to an IntegrationData."""
    return IntegrationData(
        id=row.id,
        account_id=row.account_id,
        provider=row.provider.value,
        integration_type=row.integration_type.value,
        auth_type=row.auth_type.value,
        secret_key=row.secret_key,
        created_at=row.created_at,
        business_id=row.business_id,
        raw_config=dict(row.raw_config) if row.raw_config else {},
        access_token=row.access_token,
        refresh_token=row.refresh_token,
        client_id=row.client_id,
        client_secret=row.client_secret,
        api_key=row.api_key,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
    )


class IntegrationRepository:
    """Async-only repository for Integration records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self, account_id: uuid.UUID, integration_id: uuid.UUID
    ) -> IntegrationData | None:
        """Retrieve an integration by account ID and integration ID."""
        try:
            result = await self.session.execute(
                select(Integration).filter(
                    Integration.account_id == account_id,
                    Integration.id == integration_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving integration by ID")
            raise

    async def get_by_account_id(self, account_id: uuid.UUID) -> list[IntegrationData]:
        """Retrieve all integrations for an account."""
        try:
            result = await self.session.execute(
                select(Integration).filter(Integration.account_id == account_id)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving integrations by account ID")
            raise

    async def get_by_project_and_type(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID,
        integration_type: str,
    ) -> IntegrationData | None:
        """Retrieve an integration by project ID and type."""
        integration_type_enum = IntegrationType(integration_type)
        try:
            result = await self.session.execute(
                select(Integration)
                .join(
                    ProjectIntegration,
                    Integration.id == ProjectIntegration.integration_id,
                )
                .filter(
                    Integration.account_id == account_id,
                    ProjectIntegration.project_id == project_id,
                    Integration.integration_type == integration_type_enum,
                )
                .limit(2)
            )
            rows = result.scalars().all()
            if len(rows) > 1:
                raise ValueError(
                    "Multiple integrations found for the same project and type"
                )
            return _to_data(rows[0]) if rows else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving integration by project and type")
            raise
