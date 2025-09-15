from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime

from .base import Base


class PageType(str, enum.Enum):
    """Page Type Enum for tracking different pages"""

    AGENT_DETAIL = "agent_detail"
    PROJECT_DETAIL = "project_detail"
    ACCOUNT_DETAIL = "account_detail"


class PageVersion(Base):
    """Page Version Control Table - tracks version numbers for web pages"""

    __tablename__ = "page_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )

    # Page identification
    page_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Optional page identifier (e.g., agent_id for agent detail page)
    page_identifier: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )

    # Version number for this page
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    # Metadata
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        index=True,
    )

    # Composite unique constraint to ensure one version per page
    __table_args__ = (
        Index("ix_page_versions_unique", "page_type", "page_identifier", unique=True),
    )
