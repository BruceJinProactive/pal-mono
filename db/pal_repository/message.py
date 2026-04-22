from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.message import MessageData
from db.tables.messages import Message
from utils.log import logger


def _to_data(row: Message) -> MessageData:
    """Convert an ORM Message to a MessageData."""
    return MessageData(
        id=row.id,
        conversation_id=row.conversation_id,
        body=dict(row.body) if row.body else {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class MessageRepository:
    """Async-only repository for Message records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, message_id: uuid.UUID) -> MessageData | None:
        """Retrieve a message by ID."""
        try:
            result = await self.session.execute(
                select(Message).filter(Message.id == message_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving message by ID")
            raise

    async def get_by_conversation_id(
        self, conversation_id: uuid.UUID
    ) -> list[MessageData]:
        """Retrieve all messages for a conversation, ordered by created_at."""
        try:
            result = await self.session.execute(
                select(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving messages by conversation ID")
            raise

    async def create(self, record: MessageData) -> MessageData:
        """Create a new message."""
        try:
            row = Message(
                id=record.id,
                conversation_id=record.conversation_id,
                body=dict(record.body),
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating message")
            raise
