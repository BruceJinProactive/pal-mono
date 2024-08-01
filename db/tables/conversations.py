from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import BigInteger, DateTime

from db.tables.base import Base


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")
