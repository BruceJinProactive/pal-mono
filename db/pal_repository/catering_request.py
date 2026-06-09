from __future__ import annotations

import re
import uuid
from datetime import date, time

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.pal_repository.data_classes.routine_execution import UNSET, _Unset
from db.tables.catering_requests import CateringRequest, FulfillmentType, RequestStatus
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

    async def list_by_project_id_and_phone(
        self, project_id: uuid.UUID, phone_number: str
    ) -> list[CateringRequestData]:
        """Retrieve catering requests for a project/caller phone, newest first."""
        target_digits = re.sub(r"\D", "", phone_number or "")
        if not target_digits:
            return []

        requests = await self.get_by_project_id(project_id)
        return [
            request
            for request in requests
            if re.sub(r"\D", "", request.contact_phone_number or "") == target_digits
        ]

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

    async def create(self, data: CateringRequestData) -> uuid.UUID:
        """Create a new catering request and return its persisted ID."""
        try:
            row = CateringRequest(
                id=data.id,
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
                    RequestStatus(data.status) if data.status else RequestStatus.LEAD
                ),
            )
            self.session.add(row)
            await self.session.flush()
            request_id = row.id
            await self.session.commit()
            return request_id
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating catering request")
            raise

    async def update(
        self,
        idempotency_key: str,
        event_date: date | _Unset = UNSET,
        contact_name: str | _Unset = UNSET,
        contact_phone_number: str | _Unset = UNSET,
        event_time: time | None | _Unset = UNSET,
        event_address: str | None | _Unset = UNSET,
        event_detail: str | None | _Unset = UNSET,
        event_fulfillment: FulfillmentType | None | _Unset = UNSET,
        party_size: int | None | _Unset = UNSET,
        contact_id: uuid.UUID | None | _Unset = UNSET,
        status: RequestStatus | _Unset = UNSET,
    ) -> CateringRequestData | None:
        """Update a catering request by idempotency key. Only provided fields are updated.

        Returns the updated record, or None if not found.
        """
        try:
            existing = await self.get_by_idempotency_key(idempotency_key)
            if existing is None:
                return None

            values: dict = {}
            if not isinstance(event_date, _Unset):
                values["event_date"] = event_date
            if not isinstance(contact_name, _Unset):
                values["contact_name"] = contact_name
            if not isinstance(contact_phone_number, _Unset):
                values["contact_phone_number"] = contact_phone_number
            if not isinstance(event_time, _Unset):
                values["event_time"] = event_time
            if not isinstance(event_address, _Unset):
                values["event_address"] = event_address
            if not isinstance(event_detail, _Unset):
                values["event_detail"] = event_detail
            if not isinstance(event_fulfillment, _Unset):
                values["event_fulfillment"] = event_fulfillment
            if not isinstance(party_size, _Unset):
                values["party_size"] = party_size
            if not isinstance(contact_id, _Unset):
                values["contact_id"] = contact_id
            if not isinstance(status, _Unset):
                values["status"] = status

            if values:
                await self.session.execute(
                    update(CateringRequest)
                    .where(CateringRequest.idempotency_key == idempotency_key)
                    .values(**values)
                )
                await self.session.commit()

            return await self.get_by_idempotency_key(idempotency_key)
        except Exception:
            await self.session.rollback()
            logger.exception("Error updating catering request")
            raise
