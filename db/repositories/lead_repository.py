import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables.lead import BusinessSegment, Lead, LeadStatus, TargetTier
from utils.log import logger


@dataclass
class LeadFilter:
    """Filter parameters for listing leads"""

    page: int = 1
    page_size: int = 20
    status_filter: Optional[List[LeadStatus]] = None
    segment_filter: Optional[List[BusinessSegment]] = None
    tier_filter: Optional[List[TargetTier]] = None
    keyword: Optional[str] = None


class LeadRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def get_lead_by_id(self, lead_id: uuid.UUID) -> Lead | None:
        """Retrieve a lead by its ID."""
        try:
            return (
                self.session.query(Lead)
                .filter(Lead.id == lead_id, Lead.deleted.is_not(True))
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving lead by ID: {e}")
            raise

    def list_leads_paginated(
        self,
        lead_filter: LeadFilter,
    ) -> Tuple[List[Lead], int]:
        """
        Retrieve a paginated list of leads with optional filters.

        Args:
            lead_filter: Filter parameters including pagination and search criteria

        Returns:
            Tuple of (leads list, total count)
        """
        try:
            # Build the query
            query = self.session.query(Lead).filter(Lead.deleted.is_not(True))

            # Apply filters
            if lead_filter.status_filter:
                query = query.filter(Lead.status.in_(lead_filter.status_filter))
            if lead_filter.segment_filter:
                query = query.filter(Lead.segment.in_(lead_filter.segment_filter))
            if lead_filter.tier_filter:
                query = query.filter(Lead.tier.in_(lead_filter.tier_filter))
            if lead_filter.keyword:
                keyword_pattern = f"%{lead_filter.keyword}%"
                query = query.filter(
                    (Lead.business_name.ilike(keyword_pattern))
                    | (Lead.business_address.ilike(keyword_pattern))
                    | (Lead.owner.ilike(keyword_pattern))
                    | (Lead.hubspot_record_id.ilike(keyword_pattern))
                    | (Lead.notes.ilike(keyword_pattern))
                )

            # Get total count before pagination
            total_count = query.count()

            # Apply pagination and ordering
            offset = (lead_filter.page - 1) * lead_filter.page_size
            leads = (
                query.order_by(desc(Lead.created_at))
                .offset(offset)
                .limit(lead_filter.page_size)
                .all()
            )

            return leads, total_count

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error listing leads: {e}")
            raise

    def create_lead(self, **kwargs) -> Lead:
        """Create a new lead."""
        try:
            db_lead = Lead(id=uuid.uuid4())
            for key, value in kwargs.items():
                if value is not None and hasattr(db_lead, key):
                    setattr(db_lead, key, value)

            self.session.add(db_lead)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_lead)
            return db_lead

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating lead: {e}")
            raise

    def update_lead(self, lead_id: uuid.UUID, **kwargs) -> Lead | None:
        """Update a lead by its ID."""
        try:
            db_lead = self.get_lead_by_id(lead_id)
            if not db_lead:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(db_lead, key):
                    setattr(db_lead, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_lead)
            return db_lead
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating lead: {e}")
            raise

    def delete_lead(self, lead_id: uuid.UUID):
        """Delete a lead by its ID."""
        try:
            db_lead = self.get_lead_by_id(lead_id)
            if not db_lead:
                return

            db_lead.deleted = True

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting lead: {e}")
            raise
