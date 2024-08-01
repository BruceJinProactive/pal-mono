from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import JSON, BigInteger, DateTime

from db.tables.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=False, index=True
    )
    raw_config: Mapped[dict] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="users")
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="user"
    )
