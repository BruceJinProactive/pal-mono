from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, literal_column, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from db.pal_repository.data_classes.catering_request import (
    CateringRequestCustomerHistoryData,
    CateringRequestData,
)
from db.pal_repository.data_classes.routine_execution import UNSET, _Unset
from db.tables.catering_requests import CateringRequest, FulfillmentType, RequestStatus
from db.tables.projects import Project
from utils.log import logger
from utils.phone import normalize_phone_digits


def _supports_all_items_column() -> bool:
    return hasattr(CateringRequest, "all_items")


def _normalize_contact_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def _to_data(row: CateringRequest) -> CateringRequestData:
    """Convert an ORM CateringRequest to a CateringRequestData."""
    return CateringRequestData(
        id=row.id,
        project_id=row.project_id,
        event_date=row.event_date,
        contact_name=row.contact_name,
        contact_phone_number=row.contact_phone_number,
        contact_email=row.contact_email,
        status=row.status.value if row.status else "",
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
        prior_catering_request_count=row.prior_catering_request_count,
        prior_order_count=row.prior_order_count,
        last_catering_request_at=row.last_catering_request_at,
        last_order_at=row.last_order_at,
        estimated_order_value=row.estimated_order_value,
        confirmed_order_value=row.confirmed_order_value,
        deposit_requirement_value=row.deposit_requirement_value,
        deposit_received_value=row.deposit_received_value,
        event_time=row.event_time,
        event_address=row.event_address,
        event_detail=row.event_detail,
        all_items=getattr(row, "all_items", None),
        event_fulfillment=(
            row.event_fulfillment.value if row.event_fulfillment else None
        ),
        party_size=row.party_size,
        contact_id=row.contact_id,
    )


def _phone_match_keys(phone_number: str | None) -> set[str]:
    digits = re.sub(r"\D", "", phone_number or "")
    if not digits:
        return set()

    keys = {digits}
    if len(digits) == 11 and digits.startswith("1"):
        keys.add(digits[1:])
    elif len(digits) == 10:
        keys.add(f"1{digits}")
    return keys


def _contact_phone_digits_expr() -> Any:
    return func.regexp_replace(
        func.coalesce(CateringRequest.contact_phone_number, literal_column("''")),
        literal_column(r"'\D'"),
        literal_column("''"),
        literal_column("'g'"),
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
        self, project_id: uuid.UUID, phone_number: str | None
    ) -> list[CateringRequestData]:
        """Retrieve catering requests for a project/caller phone, newest first."""
        target_keys = _phone_match_keys(phone_number)
        if not target_keys:
            return []

        contact_phone_digits = _contact_phone_digits_expr()
        try:
            result = await self.session.execute(
                select(CateringRequest)
                .filter(
                    CateringRequest.project_id == project_id,
                    contact_phone_digits.in_(target_keys),
                )
                .order_by(CateringRequest.created_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving catering requests by project and phone")
            raise

    async def get_customer_history_by_project_id_and_phone_or_email(
        self,
        project_id: uuid.UUID,
        phone_number: str | None,
        contact_email: str | None = None,
    ) -> CateringRequestCustomerHistoryData:
        """Summarize prior same-account catering requests by caller phone or email."""
        target_digits = normalize_phone_digits(phone_number)
        target_email = _normalize_contact_email(contact_email)
        if target_digits is None and target_email is None:
            return CateringRequestCustomerHistoryData(request_count=0)

        match_filters: list[Any] = []
        if target_digits is not None:
            phone_digits = func.regexp_replace(
                func.coalesce(CateringRequest.contact_phone_number, ""),
                r"\D",
                "",
                "g",
            )
            match_filters.append(phone_digits == target_digits)
        if target_email is not None:
            contact_email_normalized = func.lower(
                func.trim(func.coalesce(CateringRequest.contact_email, ""))
            )
            match_filters.append(contact_email_normalized == target_email)

        request_project = aliased(Project)
        current_project = aliased(Project)
        current_account_id = (
            select(current_project.account_id)
            .filter(current_project.id == project_id)
            .scalar_subquery()
        )
        try:
            result = await self.session.execute(
                select(
                    func.count(CateringRequest.id).label("request_count"),
                    func.max(CateringRequest.created_at).label("last_request_at"),
                )
                .join(request_project, CateringRequest.project_id == request_project.id)
                .filter(
                    request_project.account_id == current_account_id,
                    or_(*match_filters),
                )
            )
            row = result.mappings().one()
            return CateringRequestCustomerHistoryData(
                request_count=int(row["request_count"] or 0),
                last_request_at=row["last_request_at"],
            )
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving catering request customer history")
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

    async def create(self, data: CateringRequestData) -> uuid.UUID:
        """Create a new catering request and return its persisted ID."""
        try:
            values: dict[str, Any] = {
                "id": data.id,
                "project_id": data.project_id,
                "event_date": data.event_date,
                "contact_name": data.contact_name,
                "contact_phone_number": data.contact_phone_number,
                "contact_email": data.contact_email,
                "idempotency_key": data.idempotency_key,
                "prior_catering_request_count": data.prior_catering_request_count,
                "prior_order_count": data.prior_order_count,
                "last_catering_request_at": data.last_catering_request_at,
                "last_order_at": data.last_order_at,
                "estimated_order_value": data.estimated_order_value,
                "confirmed_order_value": data.confirmed_order_value,
                "deposit_requirement_value": data.deposit_requirement_value,
                "deposit_received_value": data.deposit_received_value,
                "event_time": data.event_time,
                "event_address": data.event_address,
                "event_detail": data.event_detail,
                "event_fulfillment": data.event_fulfillment,
                "party_size": data.party_size,
                "contact_id": data.contact_id,
                "status": (
                    RequestStatus(data.status) if data.status else RequestStatus.LEAD
                ),
            }
            if _supports_all_items_column():
                values["all_items"] = data.all_items

            row = CateringRequest(**values)
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
        event_date: date | None | _Unset = UNSET,
        contact_name: str | _Unset = UNSET,
        contact_phone_number: str | None | _Unset = UNSET,
        contact_email: str | None | _Unset = UNSET,
        event_time: time | None | _Unset = UNSET,
        event_address: str | None | _Unset = UNSET,
        event_detail: str | None | _Unset = UNSET,
        all_items: dict[str, dict[str, Any]] | None | _Unset = UNSET,
        event_fulfillment: FulfillmentType | None | _Unset = UNSET,
        party_size: int | None | _Unset = UNSET,
        contact_id: uuid.UUID | None | _Unset = UNSET,
        prior_catering_request_count: int | _Unset = UNSET,
        prior_order_count: int | _Unset = UNSET,
        last_catering_request_at: datetime | None | _Unset = UNSET,
        last_order_at: datetime | None | _Unset = UNSET,
        estimated_order_value: Decimal | None | _Unset = UNSET,
        confirmed_order_value: Decimal | None | _Unset = UNSET,
        deposit_requirement_value: Decimal | None | _Unset = UNSET,
        deposit_received_value: Decimal | None | _Unset = UNSET,
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
            if not isinstance(contact_email, _Unset):
                values["contact_email"] = contact_email
            if not isinstance(event_time, _Unset):
                values["event_time"] = event_time
            if not isinstance(event_address, _Unset):
                values["event_address"] = event_address
            if not isinstance(event_detail, _Unset):
                values["event_detail"] = event_detail
            if not isinstance(all_items, _Unset) and _supports_all_items_column():
                values["all_items"] = all_items
            if not isinstance(event_fulfillment, _Unset):
                values["event_fulfillment"] = event_fulfillment
            if not isinstance(party_size, _Unset):
                values["party_size"] = party_size
            if not isinstance(contact_id, _Unset):
                values["contact_id"] = contact_id
            if not isinstance(prior_catering_request_count, _Unset):
                values["prior_catering_request_count"] = prior_catering_request_count
            if not isinstance(prior_order_count, _Unset):
                values["prior_order_count"] = prior_order_count
            if not isinstance(last_catering_request_at, _Unset):
                values["last_catering_request_at"] = last_catering_request_at
            if not isinstance(last_order_at, _Unset):
                values["last_order_at"] = last_order_at
            if not isinstance(estimated_order_value, _Unset):
                values["estimated_order_value"] = estimated_order_value
            if not isinstance(confirmed_order_value, _Unset):
                values["confirmed_order_value"] = confirmed_order_value
            if not isinstance(deposit_requirement_value, _Unset):
                values["deposit_requirement_value"] = deposit_requirement_value
            if not isinstance(deposit_received_value, _Unset):
                values["deposit_received_value"] = deposit_received_value
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

    async def delete_by_id(self, request_id: uuid.UUID) -> CateringRequestData | None:
        """Delete a catering request by ID and return the deleted record."""
        try:
            existing = await self.get_by_id(request_id)
            if existing is None:
                return None

            await self.session.execute(
                delete(CateringRequest).where(CateringRequest.id == request_id)
            )
            await self.session.commit()
            return existing
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting catering request")
            raise
