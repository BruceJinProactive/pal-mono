from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Enum, String

from .base import Base
from .types import IdentifierType


class Feature(Base):
    """
    Feature flags for the gatekeeper service.
    Allows enabling/disabling features for specific entities.
    """

    __tablename__ = "features"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )

    # Feature name (e.g., 'new_ui', 'beta_api', 'experimental_feature')
    feature: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    # Type of identifier (agent, account, project, user)
    identifier_type: Mapped[IdentifierType] = mapped_column(
        Enum(IdentifierType),
        nullable=False,
    )

    # The actual identifier value (UUID or string ID)
    identifier: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    # Whether the feature is enabled
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Unique constraint on identifier_type + identifier + feature
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "identifier",
            "feature",
            name="uq_feature_identifier",
        ),
        {
            "schema": None,
            "extend_existing": True,
        },
    )

    def __repr__(self) -> str:
        return f"<Feature(feature={self.feature}, identifier_type={self.identifier_type}, identifier={self.identifier}, enabled={self.enabled})>"
