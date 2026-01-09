"""
Repository for reservation and waitlist database operations.

Data Model:
    Account (Brand) → Project (Restaurant) → Conversation → Reservation

Each reservation/waitlist entry is a separate row. Multiple entries from the
same customer are counted separately (e.g., 3 reservations = 3 rows = count of 3).

This repository handles:
    - CRUD operations for individual reservations/waitlist entries
    - Analytics queries filtered by project (restaurant) and timeframe

Note: Status updates (e.g., "seated") are NOT tracked via webhooks in Phase 1.
      We only record the initial "joined waitlist" or "made reservation" event.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import Conversation
from db.tables.reservations import Reservation
from db.tables.types import IntegrationProvider
from utils.log import logger


class ReservationRepository:
    """Repository for managing reservation and waitlist database operations."""

    def __init__(self, session: Session, auto_commit: bool = True):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session (injected by caller)
            auto_commit: If True, commits after each write operation.
                        Set False to batch operations in one transaction.
        """
        self.session = session
        self.auto_commit = auto_commit

    # ==========================================================================
    # CRUD Operations
    # No try/except - failures should propagate to caller (service layer)
    # ==========================================================================

    def create_reservation(
        self,
        conversation_id: uuid.UUID,
        entry_type: str = "reservation",
        vendor: Optional[IntegrationProvider] = None,
        reservation_id: Optional[str] = None,
        store_id: Optional[str] = None,
        tracking_link: Optional[str] = None,
        status: Optional[str] = None,
        table_size: Optional[int] = None,
        special_requests: Optional[str] = None,
        reservation_time: Optional[datetime] = None,
        arrive_by_time: Optional[datetime] = None,
        expected_seating_time: Optional[datetime] = None,
    ) -> Reservation:
        """
        Create a new reservation or waitlist entry.

        Each call creates a NEW row with a unique UUID. Multiple reservations
        from the same customer result in multiple rows (counted separately).

        Args:
            conversation_id: The conversation this entry belongs to (required)
            entry_type: "reservation" or "waitlist" (default: "reservation")
            vendor: The integration provider (yelp, minitable, resy, opentable)
            reservation_id: Identifier from external system (visit_id, waitlist_id)
            store_id: Store/location identifier from external system
            tracking_link: URL to manage the entry (e.g., MiniTable status_link)
            status: Current status ("queued", "confirmed", etc.)
            table_size: Number of people in the party
            special_requests: Customer notes/requests
            reservation_time: When the reservation is for (future datetime)
            arrive_by_time: When customer should arrive (Yelp waitlist)
            expected_seating_time: Estimated seating time (Yelp waitlist)

        Returns:
            Reservation: The created record with generated UUID
        """
        reservation = Reservation(
            conversation_id=conversation_id,
            entry_type=entry_type,
            vendor=vendor,
            reservation_id=reservation_id,
            store_id=store_id,
            tracking_link=tracking_link,
            status=status,
            table_size=table_size,
            special_requests=special_requests,
            reservation_time=reservation_time,
            arrive_by_time=arrive_by_time,
            expected_seating_time=expected_seating_time,
        )
        self.session.add(reservation)
        if self.auto_commit:
            self.session.commit()
        return reservation

    def get_by_id(self, reservation_uuid: uuid.UUID) -> Optional[Reservation]:
        """Get a reservation/waitlist entry by its primary key UUID."""
        return (
            self.session.query(Reservation)
            .filter(Reservation.id == reservation_uuid)
            .first()
        )

    def get_by_conversation_id(self, conversation_id: uuid.UUID) -> list[Reservation]:
        """
        Get all reservations/waitlist entries for a conversation.

        A single conversation may have multiple entries (e.g., customer
        changed their mind and rebooked). Returns newest first.
        """
        return (
            self.session.query(Reservation)
            .filter(Reservation.conversation_id == conversation_id)
            .order_by(Reservation.created_at.desc())
            .all()
        )

    def get_by_external_id(
        self,
        reservation_id: str,
        vendor: IntegrationProvider,
        store_id: Optional[str] = None,
    ) -> Optional[Reservation]:
        """
        Get a reservation/waitlist entry by its external system ID.

        Use this when you have the vendor's ID (e.g., Yelp visit_id) but not
        our internal UUID. Useful for webhook callbacks or reconciliation.

        Args:
            reservation_id: External system identifier (visit_id, waitlist_id)
            vendor: The integration provider (yelp, minitable, etc.)
            store_id: Optional store ID for additional filtering

        Returns:
            Reservation if found, None otherwise
        """
        query = self.session.query(Reservation).filter(
            Reservation.reservation_id == reservation_id,
            Reservation.vendor == vendor,
        )
        if store_id:
            query = query.filter(Reservation.store_id == store_id)
        return query.first()

    def update(
        self,
        reservation_uuid: uuid.UUID,
        **kwargs,
    ) -> Optional[Reservation]:
        """
        Update a reservation/waitlist entry by its primary key UUID.

        Args:
            reservation_uuid: The internal UUID
            **kwargs: Fields to update (status, tracking_link, etc.)

        Returns:
            Updated Reservation if found, None otherwise
        """
        reservation = self.get_by_id(reservation_uuid)
        if reservation:
            for field, value in kwargs.items():
                if hasattr(reservation, field):
                    setattr(reservation, field, value)
            if self.auto_commit:
                self.session.commit()
        return reservation

    def update_by_external_id(
        self,
        reservation_id: str,
        vendor: IntegrationProvider,
        store_id: Optional[str] = None,
        **kwargs,
    ) -> Optional[Reservation]:
        """
        Update a reservation/waitlist entry by its external system ID.

        Useful for future webhook integration when we receive status updates
        from Yelp/MiniTable with only their ID.

        Args:
            reservation_id: External system identifier
            vendor: The integration provider
            store_id: Optional store ID for filtering
            **kwargs: Fields to update

        Returns:
            Updated Reservation if found, None otherwise
        """
        reservation = self.get_by_external_id(reservation_id, vendor, store_id)
        if reservation:
            for field, value in kwargs.items():
                if hasattr(reservation, field):
                    setattr(reservation, field, value)
            if self.auto_commit:
                self.session.commit()
        return reservation

    # ==========================================================================
    # Analytics Methods
    # With try/except for graceful degradation - complex queries shouldn't
    # crash the app if they fail. Return empty/default data on error.
    #
    # Analytics are queried PER RESTAURANT (project_id) BY TIMEFRAME.
    # JOIN chain: Reservation → Conversation (filter by Conversation.project_id)
    #
    # Each row is counted separately - multiple reservations from same customer
    # at same store = multiple counts.
    # ==========================================================================

    def get_reservation_summary(
        self,
        project_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        """
        Get reservation and waitlist summary metrics for a restaurant.

        Each reservation/waitlist entry is counted separately. If a customer
        made 3 reservations, that counts as 3.

        Args:
            project_id: The restaurant/project UUID
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            dict with:
                - total_reservations: Count where entry_type='reservation'
                - total_waitlists: Count where entry_type='waitlist'
                - by_vendor: {"yelp": 5, "minitable": 3, ...}
                - by_status: {"queued": 4, "confirmed": 2, ...}
        """
        try:
            # Common filters for all queries
            base_filters = [
                Conversation.project_id == project_id,
                Reservation.created_at >= start_date,
                Reservation.created_at <= end_date,
            ]

            # Helper to build count queries
            def count_with_filters(*extra_filters):
                return (
                    self.session.query(func.count(Reservation.id))
                    .join(
                        Conversation,
                        Reservation.conversation_id == Conversation.id,
                    )
                    .filter(*base_filters, *extra_filters)
                    .scalar()
                ) or 0

            # Count by entry_type
            total_reservations = count_with_filters(
                Reservation.entry_type == "reservation"
            )
            total_waitlists = count_with_filters(Reservation.entry_type == "waitlist")

            # Count by vendor (group by)
            vendor_results = (
                self.session.query(
                    Reservation.vendor,
                    func.count(Reservation.id),
                )
                .join(
                    Conversation,
                    Reservation.conversation_id == Conversation.id,
                )
                .filter(*base_filters)
                .group_by(Reservation.vendor)
                .all()
            )
            by_vendor = {
                (v.value if v else "unknown"): count for v, count in vendor_results
            }

            # Count by status (group by)
            status_results = (
                self.session.query(
                    Reservation.status,
                    func.count(Reservation.id),
                )
                .join(
                    Conversation,
                    Reservation.conversation_id == Conversation.id,
                )
                .filter(*base_filters)
                .group_by(Reservation.status)
                .all()
            )
            by_status = {(s or "unknown"): count for s, count in status_results}

            return {
                "total_reservations": total_reservations,
                "total_waitlists": total_waitlists,
                "by_vendor": by_vendor,
                "by_status": by_status,
            }

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"[ReservationRepository] Error getting reservation summary "
                f"for project {project_id}: {e}"
            )
            return {
                "total_reservations": 0,
                "total_waitlists": 0,
                "by_vendor": {},
                "by_status": {},
            }

    def get_reservation_counts_by_date(
        self,
        project_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """
        Get daily reservation/waitlist counts for a restaurant.
        Used for time-series charts in dashboards.

        Each row is counted separately per day.

        Args:
            project_id: The restaurant/project UUID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of Row objects with: (date, entry_type, vendor, count)
            Example: [
                (date(2024-01-15), "waitlist", IntegrationProvider.yelp, 5),
                (date(2024-01-15), "reservation", IntegrationProvider.minitable, 2),
                (date(2024-01-16), "waitlist", IntegrationProvider.yelp, 3),
                ...
            ]
        """
        try:
            date_expr = func.date(Reservation.created_at)

            query = (
                select(
                    date_expr.label("date"),
                    Reservation.entry_type,
                    Reservation.vendor,
                    func.count(Reservation.id).label("count"),
                )
                .join(
                    Conversation,
                    Reservation.conversation_id == Conversation.id,
                )
                .filter(
                    Conversation.project_id == project_id,
                    Reservation.created_at >= start_date,
                    Reservation.created_at <= end_date,
                )
                .group_by(
                    date_expr,
                    Reservation.entry_type,
                    Reservation.vendor,
                )
                .order_by(date_expr)
            )

            result = self.session.execute(query)
            return list(result.all())

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"[ReservationRepository] Error getting reservation counts by date "
                f"for project {project_id}: {e}"
            )
            return []
