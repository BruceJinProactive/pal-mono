from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.reservations import Reservation
from db.tables.types import IntegrationProvider
from pal_repository.data_classes.reservation import ReservationData
from utils.log import logger


def _to_data(row: Reservation) -> ReservationData:
    """Convert an ORM Reservation to a ReservationData.

    Enum fields are converted to their string values so the record does not
    expose ``db.tables.types`` to consumers.
    """
    return ReservationData(
        id=row.id,
        conversation_id=row.conversation_id,
        entry_type=row.entry_type,
        created_at=row.created_at,
        updated_at=row.updated_at,
        reservation_id=row.reservation_id,
        store_id=row.store_id,
        tracking_link=row.tracking_link,
        status=row.status,
        vendor=row.vendor.value if row.vendor else None,
        table_size=row.table_size,
        special_requests=row.special_requests,
        arrive_by_time=row.arrive_by_time,
        expected_seating_time=row.expected_seating_time,
        reservation_time=row.reservation_time,
    )


class ReservationRepository:
    """Async-only repository for Reservation records.

    All methods return ``ReservationData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, reservation_id: uuid.UUID) -> ReservationData | None:
        """Retrieve a reservation by its primary key."""
        try:
            result = await self.session.execute(
                select(Reservation).filter(Reservation.id == reservation_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving reservation by ID: {e}")
            raise

    async def get_by_conversation_id(
        self, conversation_id: uuid.UUID
    ) -> list[ReservationData]:
        """Retrieve all reservations for a given conversation."""
        try:
            result = await self.session.execute(
                select(Reservation).filter(
                    Reservation.conversation_id == conversation_id
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving reservations by conversation ID: {e}")
            raise

    async def create(self, record: ReservationData) -> None:
        """Create a new reservation.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = Reservation(
                id=record.id,
                conversation_id=record.conversation_id,
                entry_type=record.entry_type,
                reservation_id=record.reservation_id,
                store_id=record.store_id,
                tracking_link=record.tracking_link,
                status=record.status,
                vendor=(IntegrationProvider(record.vendor) if record.vendor else None),
                table_size=record.table_size,
                special_requests=record.special_requests,
                arrive_by_time=record.arrive_by_time,
                expected_seating_time=record.expected_seating_time,
                reservation_time=record.reservation_time,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating reservation: {e}")
            raise

    async def update(
        self,
        reservation_id: uuid.UUID,
        record: ReservationData,
    ) -> None:
        """Update an existing reservation.

        Fields from *record* that are non-None overwrite the existing values.
        """
        try:
            result = await self.session.execute(
                select(Reservation).filter(Reservation.id == reservation_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            if record.reservation_id is not None:
                row.reservation_id = record.reservation_id
            if record.store_id is not None:
                row.store_id = record.store_id
            if record.tracking_link is not None:
                row.tracking_link = record.tracking_link
            if record.status is not None:
                row.status = record.status
            if record.vendor is not None:
                row.vendor = IntegrationProvider(record.vendor)
            if record.table_size is not None:
                row.table_size = record.table_size
            if record.special_requests is not None:
                row.special_requests = record.special_requests
            if record.arrive_by_time is not None:
                row.arrive_by_time = record.arrive_by_time
            if record.expected_seating_time is not None:
                row.expected_seating_time = record.expected_seating_time
            if record.reservation_time is not None:
                row.reservation_time = record.reservation_time
            row.entry_type = record.entry_type

            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating reservation: {e}")
            raise

    async def delete(self, reservation_id: uuid.UUID) -> ReservationData | None:
        """Delete a reservation by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(Reservation).filter(Reservation.id == reservation_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting reservation: {e}")
            raise
