from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.tool_call_record import ToolCallRecordData
from db.tables.tool_call_records import ToolCallRecord
from utils.log import logger


def _to_data(row: ToolCallRecord) -> ToolCallRecordData:
    """Convert an ORM ToolCallRecord to a ToolCallRecordData."""
    return ToolCallRecordData(
        id=row.id,
        conversation_id=row.conversation_id,
        tool_name=row.tool_name,
        is_error=row.is_error,
        created_at=row.created_at,
        error_type=row.error_type,
        duration_ms=row.duration_ms,
        result=row.result,
    )


class ToolCallRecordRepository:
    """Async-only repository for ToolCallRecord records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_conversation_id(
        self, conversation_id: uuid.UUID
    ) -> list[ToolCallRecordData]:
        """Retrieve all tool call records for a conversation."""
        try:
            result = await self.session.execute(
                select(ToolCallRecord)
                .filter(ToolCallRecord.conversation_id == conversation_id)
                .order_by(ToolCallRecord.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving tool call records")
            raise

    async def create(self, record: ToolCallRecordData) -> ToolCallRecordData:
        """Create a new tool call record."""
        try:
            row = ToolCallRecord(
                id=record.id,
                conversation_id=record.conversation_id,
                tool_name=record.tool_name,
                is_error=record.is_error,
                created_at=record.created_at,
                error_type=record.error_type,
                duration_ms=record.duration_ms,
                result=record.result,
            )
            self.session.add(row)
            await self.session.flush()
            await self.session.refresh(row)
            return _to_data(row)
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error creating tool call record")
            raise
