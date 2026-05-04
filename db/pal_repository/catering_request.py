from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.tables.catering_requests import CateringRequest, RequestStatus
from utils.log import logger


def _to_data(row: CateringRequest) -> CateringRequestData:
    """Convert an ORM CateringRequest to a CateringRequestData."""
    return CateringRequestData(
        id=row.id,
        project_id=row.project_id,
        event_date=row.event_date,
        contact_name=row.contact_name,
        contact_phone_number=row.contact_phone_number,
        status=row.status.value if row.status else "",
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
        event_time=row.event_time,
        event_address=row.event_address,
        event_detail=row.event_detail,
        event_fulfillment=(
            row.event_fulfillment.value if row.event_fulfillment else None
        ),
        party_size=row.party_size,
        contact_id=row.contact_id,
    )


class CateringRequestRepository:
    """Async-only repository for CateringRequest records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, request_id: uuid.UUID) -> CateringRequestData | None:
        """Retrieve a catering request by ID."""
        try:
            result = await self.session.execute(
                select(CateringRequest).filter(CateringRequest.id == request_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving catering request by ID")
            raise

    async def get_by_project_id(
        self, project_id: uuid.UUID
    ) -> list[CateringRequestData]:
        """Retrieve all catering requests for a project."""
        try:
            result = await self.session.execute(
                select(CateringRequest)
                .filter(CateringRequest.project_id == project_id)
                .order_by(CateringRequest.created_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving catering requests by project")
            raise

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> CateringRequestData | None:
        """Retrieve a catering request by its idempotency key."""
        try:
            result = await self.session.execute(
                select(CateringRequest).filter(
                    CateringRequest.idempotency_key == idempotency_key
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving catering request by idempotency key")
            raise

    async def create(self, data: CateringRequestData) -> None:
        """Create a new catering request."""
        try:
            row = CateringRequest(
                project_id=data.project_id,
                event_date=data.event_date,
                contact_name=data.contact_name,
                contact_phone_number=data.contact_phone_number,
                idempotency_key=data.idempotency_key,
                event_time=data.event_time,
                event_address=data.event_address,
                event_detail=data.event_detail,
                event_fulfillment=data.event_fulfillment,
                party_size=data.party_size,
                contact_id=data.contact_id,
                status=(
                    RequestStatus(data.status) if data.status else RequestStatus.INQUIRY
                ),
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating catering request")
            raise
