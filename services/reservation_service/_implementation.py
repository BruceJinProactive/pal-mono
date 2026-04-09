"""
Reservation service implementation.

Handles saving reservation and waitlist entries, and updating customer_converted
when a conversion event occurs.

Conversion Triggers:
    - Waitlist: status == "queued" → customer converted
    - Reservation: status == "confirmed" → customer converted
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from agent.tool import ToolMetadata
from db.repositories import (
    ConversationRepository,
    OrderRepository,
    ReservationRepository,
)
from db.repositories.conversation_repository import ConversationUpdate
from db.session import SyncSessionLocal
from db.tables.reservations import Reservation
from db.tables.types import IntegrationProvider
from utils.log import logger

from .schema import ReservationData


def _update_customer_converted(
    session: Session, conversation_id: uuid.UUID, reservation_id: uuid.UUID
) -> bool:
    """
    Update the customer_converted field in the conversation with the reservation ID.

    Only updates if customer_converted is not already set to an order.
    Precedence: Paid Order > Reservation > Waitlist

    Args:
        session: Database session
        conversation_id: The conversation ID to update
        reservation_id: The reservation ID to set as customer_converted

    Returns:
        bool: True if update was successful or skipped (order takes precedence),
              False if conversation not found or error occurred
    """
    try:
        conversation_repo = ConversationRepository(session)

        # Check if already converted to a higher-precedence event (paid order)
        conversation = conversation_repo.get_conversation_by_id(conversation_id)
        if conversation and conversation.customer_converted:
            order_repo = OrderRepository(session, auto_commit=False)
            existing_order = order_repo.get_order_by_id(conversation.customer_converted)
            if existing_order:
                logger.info(
                    f"[ReservationService] Skipping customer_converted update for "
                    f"conversation {conversation_id}: already has order "
                    f"{conversation.customer_converted}"
                )
                return True  # Already converted via order, no need to update

        # Update with reservation ID (either NULL or existing reservation/waitlist)
        update_data = ConversationUpdate(customer_converted=reservation_id)

        updated_conversation = conversation_repo.update_conversation(
            conversation_id=conversation_id,
            update_data=update_data,
        )

        if updated_conversation:
            logger.info(
                f"[ReservationService] Updated customer_converted for conversation "
                f"{conversation_id} with reservation {reservation_id}"
            )
            return True
        else:
            logger.warning(
                f"[ReservationService] Failed to update customer_converted: "
                f"conversation {conversation_id} not found"
            )
            return False

    except Exception as e:
        logger.error(
            f"[ReservationService] Error updating customer_converted for "
            f"conversation {conversation_id}: {e}",
            exc_info=True,
        )
        return False


def create_reservation(
    session: Session,
    reservation_data: ReservationData,
) -> Reservation:
    """Create a new reservation/waitlist record from standardized data."""
    repository = ReservationRepository(session, auto_commit=True)
    return repository.create_reservation(
        conversation_id=reservation_data.conversation_id,
        entry_type=reservation_data.entry_type,
        vendor=reservation_data.vendor,
        reservation_id=reservation_data.reservation_id,
        store_id=reservation_data.store_id,
        tracking_link=reservation_data.tracking_link,
        status=reservation_data.status,
        table_size=reservation_data.table_size,
        special_requests=reservation_data.special_requests,
        reservation_time=reservation_data.reservation_time,
        arrive_by_time=reservation_data.arrive_by_time,
        expected_seating_time=reservation_data.expected_seating_time,
    )


def get_reservation_by_id(
    session: Session,
    reservation_uuid: uuid.UUID,
) -> Optional[Reservation]:
    """Get a reservation by its internal UUID."""
    repository = ReservationRepository(session, auto_commit=False)
    return repository.get_by_id(reservation_uuid)


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
    Save a waitlist entry to the reservations table.

    This is a convenience function for tools to easily save waitlist data
    without having to handle database sessions and data structures.

    Conversion Trigger: If status == "queued", updates customer_converted.

    Args:
        tool_metadata: Tool metadata containing session_id (conversation_id)
        vendor: The integration provider (yelp, minitable, etc.)
        reservation_id: Waitlist/visit ID from external system
        store_id: Store/location identifier
        status: Waitlist status (default: "queued")
        tracking_link: URL to view/manage the waitlist entry
        table_size: Number of people in party
        special_requests: Customer notes/requests
        arrive_by_time: When customer should arrive
        expected_seating_time: Estimated seating time
        session: Optional database session (creates one if not provided)

    Returns:
        uuid.UUID: The ID of the created entry, or None if failed
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        reservation_data = ReservationData(
            conversation_id=tool_metadata.session_id,
            vendor=vendor,
            entry_type="waitlist",
            reservation_id=reservation_id,
            store_id=store_id,
            status=status,
            tracking_link=tracking_link,
            table_size=table_size,
            special_requests=special_requests,
            arrive_by_time=arrive_by_time,
            expected_seating_time=expected_seating_time,
        )

        reservation = create_reservation(db_session, reservation_data)

        logger.info(
            f"[ReservationService] Saved waitlist entry {reservation.id} "
            f"for {vendor} with reservation_id {reservation_id}"
        )

        # If status is "queued", customer has converted (joined waitlist)
        if status and status.lower() == "queued":
            _update_customer_converted(
                session=db_session,
                conversation_id=reservation.conversation_id,
                reservation_id=reservation.id,
            )

        return reservation.id

    except Exception as e:
        logger.error(
            f"[ReservationService] Failed to save waitlist for {vendor}: {e}",
            exc_info=True,
        )
        return None

    finally:
        if auto_close_session:
            db_session.close()


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
    Save a reservation to the reservations table.

    This is a convenience function for tools to easily save reservation data
    without having to handle database sessions and data structures.

    Conversion Trigger: If status == "confirmed", updates customer_converted.

    Args:
        tool_metadata: Tool metadata containing session_id (conversation_id)
        vendor: The integration provider (resy, opentable, minitable, etc.)
        reservation_id: Reservation ID from external system
        store_id: Store/location identifier
        status: Reservation status (default: "confirmed")
        tracking_link: URL to view/manage the reservation
        table_size: Number of people in party
        special_requests: Customer notes/requests
        reservation_time: When the reservation is scheduled for
        session: Optional database session (creates one if not provided)

    Returns:
        uuid.UUID: The ID of the created entry, or None if failed
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        reservation_data = ReservationData(
            conversation_id=tool_metadata.session_id,
            vendor=vendor,
            entry_type="reservation",
            reservation_id=reservation_id,
            store_id=store_id,
            status=status,
            tracking_link=tracking_link,
            table_size=table_size,
            special_requests=special_requests,
            reservation_time=reservation_time,
        )

        reservation = create_reservation(db_session, reservation_data)

        logger.info(
            f"[ReservationService] Saved reservation {reservation.id} "
            f"for {vendor} with reservation_id {reservation_id}"
        )

        # If status is "confirmed", customer has converted (made reservation)
        if status and status.lower() == "confirmed":
            _update_customer_converted(
                session=db_session,
                conversation_id=reservation.conversation_id,
                reservation_id=reservation.id,
            )

        return reservation.id

    except Exception as e:
        logger.error(
            f"[ReservationService] Failed to save reservation for {vendor}: {e}",
            exc_info=True,
        )
        return None

    finally:
        if auto_close_session:
            db_session.close()


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

    Useful for webhook callbacks or status update scenarios where we receive
    the vendor's ID but not our internal UUID.

    Args:
        reservation_id: External system identifier (visit_id, waitlist_id)
        vendor: The integration provider
        store_id: Optional store ID for additional filtering
        new_status: New status to set
        tracking_link: Optional new tracking link
        session: Optional database session (creates one if not provided)

    Returns:
        bool: True if found and updated, False otherwise
    """
    db_session = session or SyncSessionLocal()
    session_created_here = session is None

    try:
        repository = ReservationRepository(db_session, auto_commit=session_created_here)

        # Build update fields
        update_fields = {}
        if new_status is not None:
            update_fields["status"] = new_status
        if tracking_link is not None:
            update_fields["tracking_link"] = tracking_link

        if not update_fields:
            logger.warning(
                "[ReservationService] update_reservation_by_external_id called "
                "with no fields to update"
            )
            return False

        updated_reservation = repository.update_by_external_id(
            reservation_id=reservation_id,
            vendor=vendor,
            store_id=store_id,
            **update_fields,
        )

        if updated_reservation:
            logger.debug(
                f"[ReservationService] Updated reservation {updated_reservation.id} "
                f"for external_id {reservation_id}"
            )

            # Check if this status update triggers a conversion
            # Waitlist: "queued" triggers conversion
            # Reservation: "confirmed" triggers conversion
            if new_status:
                is_waitlist_conversion = (
                    updated_reservation.entry_type == "waitlist"
                    and new_status.lower() == "queued"
                )
                is_reservation_conversion = (
                    updated_reservation.entry_type == "reservation"
                    and new_status.lower() == "confirmed"
                )

                if is_waitlist_conversion or is_reservation_conversion:
                    _update_customer_converted(
                        session=db_session,
                        conversation_id=updated_reservation.conversation_id,
                        reservation_id=updated_reservation.id,
                    )

            return True
        else:
            criteria = f"reservation_id: {reservation_id}, vendor: {vendor}"
            if store_id:
                criteria += f", store_id: {store_id}"
            logger.warning(f"[ReservationService] No reservation found with {criteria}")
            return False

    except Exception as e:
        logger.error(
            f"[ReservationService] Error updating reservation {reservation_id}: {e}",
            exc_info=True,
        )
        return False

    finally:
        if session_created_here:
            db_session.close()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a datetime string (ISO 8601 or Unix epoch) to a datetime object."""
    if not value:
        return None
    # Try ISO 8601 first
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    # Try Unix epoch (integer or float as string)
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        logger.warning(
            f"[ReservationService] Could not parse datetime value: {value!r}"
        )
        return None


async def save_reservation_from_agent_async(
    session: AsyncSession,
    reservation_details: Any,
    conversation_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """
    Save a reservation/waitlist from pal-agents reservation_details.

    Maps ReservationDetails (pal-agents) -> ReservationData (pal-mono),
    persists to the reservations table, and triggers customer_converted update.

    Args:
        session: Async database session
        reservation_details: ReservationDetails object from pal-agents Output
        conversation_id: The conversation ID this reservation belongs to

    Returns:
        uuid.UUID: The created reservation ID, or None if failed
    """
    try:
        # Convert vendor string to IntegrationProvider enum
        try:
            vendor_enum = IntegrationProvider(reservation_details.vendor.lower())
        except ValueError:
            logger.warning(
                f"[ReservationService] Unknown vendor: {reservation_details.vendor}",
                extra={"vendor": reservation_details.vendor},
            )
            return None

        reservation_data = ReservationData(
            conversation_id=conversation_id,
            vendor=vendor_enum,
            entry_type=reservation_details.entry_type,
            reservation_id=reservation_details.reservation_id,
            store_id=reservation_details.store_id,
            status=reservation_details.status,
            tracking_link=reservation_details.tracking_link,
            table_size=reservation_details.party_size,
            special_requests=reservation_details.notes,
            reservation_time=_parse_datetime(reservation_details.reservation_time),
            arrive_by_time=_parse_datetime(reservation_details.arrive_by_time),
            expected_seating_time=_parse_datetime(
                reservation_details.expected_seating_time
            ),
        )

        def _save(sync_session: Session) -> Reservation:
            repository = ReservationRepository(sync_session, auto_commit=False)
            reservation = repository.create_reservation(
                conversation_id=reservation_data.conversation_id,
                entry_type=reservation_data.entry_type,
                vendor=reservation_data.vendor,
                reservation_id=reservation_data.reservation_id,
                store_id=reservation_data.store_id,
                tracking_link=reservation_data.tracking_link,
                status=reservation_data.status,
                table_size=reservation_data.table_size,
                special_requests=reservation_data.special_requests,
                reservation_time=reservation_data.reservation_time,
                arrive_by_time=reservation_data.arrive_by_time,
                expected_seating_time=reservation_data.expected_seating_time,
            )

            # Trigger customer_converted based on entry type + status
            should_convert = (
                reservation_data.entry_type == "reservation"
                and reservation_data.status
                and reservation_data.status.lower() == "confirmed"
            ) or (
                reservation_data.entry_type == "waitlist"
                and reservation_data.status
                and reservation_data.status.lower() == "queued"
            )
            if should_convert:
                _update_customer_converted(
                    session=sync_session,
                    conversation_id=conversation_id,
                    reservation_id=reservation.id,
                )

            return reservation

        reservation = await session.run_sync(_save)
        await session.commit()

        logger.info(
            f"[ReservationService] Saved {reservation_data.entry_type} "
            f"{reservation.id} for {vendor_enum} "
            f"(reservation_id={reservation_details.reservation_id})",
            extra={
                "conversation_id": str(conversation_id),
                "entry_type": reservation_data.entry_type,
                "vendor": str(vendor_enum),
                "reservation_id": reservation_details.reservation_id,
                "status": reservation_data.status,
            },
        )

        return reservation.id

    except Exception as e:
        await session.rollback()
        logger.error(
            f"[ReservationService] Failed to persist reservation from agent: {e}",
            extra={"conversation_id": str(conversation_id), "error": str(e)},
            exc_info=True,
        )
        return None
