"""
Reservation Service

A generic service for managing reservation and waitlist data across all
integration providers. Provides a standardized way to save, retrieve, and
update reservation/waitlist records from tools like Yelp, MiniTable, Resy,
OpenTable, etc.

Conversion Triggers:
    - Waitlist: status == "queued" → customer_converted updated
    - Reservation: status == "confirmed" → customer_converted updated
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from agent.tool import ToolMetadata
from db.tables.reservations import Reservation
from db.tables.types import IntegrationProvider

from . import _implementation
from .schema import ReservationData


def create_reservation(
    session: Session,
    reservation_data: ReservationData,
) -> Reservation:
    """
    Create a new reservation/waitlist record from standardized data.

    Args:
        session: Database session
        reservation_data: Standardized reservation data

    Returns:
        Reservation: The created reservation record
    """
    return _implementation.create_reservation(session, reservation_data)


def get_reservation_by_id(
    session: Session,
    reservation_uuid: uuid.UUID,
) -> Optional[Reservation]:
    """
    Get a reservation by its internal UUID.

    Args:
        session: Database session
        reservation_uuid: The UUID of the reservation to retrieve

    Returns:
        Reservation | None: The reservation if found, None otherwise
    """
    return _implementation.get_reservation_by_id(session, reservation_uuid)


def save_waitlist(
    tool_metadata: ToolMetadata,
    vendor: IntegrationProvider,
    reservation_id: Optional[str] = None,
    store_id: Optional[str] = None,
    status: Optional[str] = "queued",
    tracking_link: Optional[str] = None,
    table_size: Optional[int] = None,
    special_requests: Optional[str] = None,
    arrive_by_time: Optional[datetime] = None,
    expected_seating_time: Optional[datetime] = None,
    session: Optional[Session] = None,
) -> Optional[uuid.UUID]:
    """
    Save a waitlist entry - convenience function for tools.

    Args:
        tool_metadata: Tool metadata containing session_id
        vendor: The integration provider
        reservation_id: Waitlist/visit ID from external system
        store_id: Store/location identifier
        status: Waitlist status (default: "queued")
        tracking_link: URL to manage entry
        table_size: Number of people in party
        special_requests: Customer notes
        arrive_by_time: When customer should arrive
        expected_seating_time: Estimated seating time
        session: Optional database session

    Returns:
        uuid.UUID: The ID of the created entry, or None if failed
    """
    return _implementation.save_waitlist(
        tool_metadata=tool_metadata,
        vendor=vendor,
        reservation_id=reservation_id,
        store_id=store_id,
        status=status,
        tracking_link=tracking_link,
        table_size=table_size,
        special_requests=special_requests,
        arrive_by_time=arrive_by_time,
        expected_seating_time=expected_seating_time,
        session=session,
    )


def save_reservation(
    tool_metadata: ToolMetadata,
    vendor: IntegrationProvider,
    reservation_id: Optional[str] = None,
    store_id: Optional[str] = None,
    status: Optional[str] = "confirmed",
    tracking_link: Optional[str] = None,
    table_size: Optional[int] = None,
    special_requests: Optional[str] = None,
    reservation_time: Optional[datetime] = None,
    session: Optional[Session] = None,
) -> Optional[uuid.UUID]:
    """
    Save a reservation - convenience function for tools.

    Args:
        tool_metadata: Tool metadata containing session_id
        vendor: The integration provider
        reservation_id: Reservation ID from external system
        store_id: Store/location identifier
        status: Reservation status (default: "confirmed")
        tracking_link: URL to manage reservation
        table_size: Number of people in party
        special_requests: Customer notes
        reservation_time: When reservation is scheduled for
        session: Optional database session

    Returns:
        uuid.UUID: The ID of the created entry, or None if failed
    """
    return _implementation.save_reservation(
        tool_metadata=tool_metadata,
        vendor=vendor,
        reservation_id=reservation_id,
        store_id=store_id,
        status=status,
        tracking_link=tracking_link,
        table_size=table_size,
        special_requests=special_requests,
        reservation_time=reservation_time,
        session=session,
    )


async def save_reservation_from_agent_async(
    session: AsyncSession,
    reservation_details: Any,
    conversation_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """
    Save a reservation/waitlist from pal-agents reservation_details.

    Args:
        session: Async database session
        reservation_details: ReservationDetails object from pal-agents Output
        conversation_id: The conversation ID this reservation belongs to

    Returns:
        uuid.UUID: The created reservation ID, or None if failed
    """
    return await _implementation.save_reservation_from_agent_async(
        session=session,
        reservation_details=reservation_details,
        conversation_id=conversation_id,
    )


def update_reservation_by_external_id(
    reservation_id: str,
    vendor: IntegrationProvider,
    store_id: Optional[str] = None,
    new_status: Optional[str] = None,
    tracking_link: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Update a reservation/waitlist by its external system ID.

    Args:
        reservation_id: External system identifier
        vendor: The integration provider
        store_id: Optional store ID for filtering
        new_status: New status to set
        tracking_link: Optional new tracking link
        session: Optional database session

    Returns:
        bool: True if found and updated, False otherwise
    """
    return _implementation.update_reservation_by_external_id(
        reservation_id=reservation_id,
        vendor=vendor,
        store_id=store_id,
        new_status=new_status,
        tracking_link=tracking_link,
        session=session,
    )


__all__ = [
    "ReservationData",
    "create_reservation",
    "get_reservation_by_id",
    "save_reservation",
    "save_reservation_from_agent_async",
    "save_waitlist",
    "update_reservation_by_external_id",
]
