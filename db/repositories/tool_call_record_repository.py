import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import ToolCallRecord
from utils.log import logger


class ToolCallRecordRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_tool_call_record(
        self,
        conversation_id: uuid.UUID,
        tool_name: str,
        is_error: bool,
        error_type: str | None = None,
        duration_ms: int | None = None,
        result: str | None = None,
    ) -> ToolCallRecord | None:
        """
        Insert a tool call record. Fire-and-forget — returns None on failure.

        Args:
            conversation_id: The UUID of the conversation this tool call belongs to.
            tool_name: Name of the tool that was called.
            is_error: Whether the tool call resulted in an error.
            error_type: Optional error type (e.g., "TypeError", "APIError").
            duration_ms: Optional duration in milliseconds for performance analysis.
            result: Optional output/error message. Truncated to 1000 chars if longer.
                    CALLER MUST sanitize PII before passing - this method stores verbatim.

        Returns:
            ToolCallRecord | None: The created record if successful, None if an error occurs.
        """
        try:
            record = ToolCallRecord(
                conversation_id=conversation_id,
                tool_name=tool_name,
                is_error=is_error,
                error_type=error_type,
                duration_ms=duration_ms,
                result=result[:1000] if result and len(result) > 1000 else result,
            )
            self.session.add(record)
            await self.session.commit()
            await self.session.refresh(record)
            return record
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error adding tool call record: {e}")
            return None

    async def get_tool_calls_by_conversation(
        self, conversation_id: uuid.UUID
    ) -> list[ToolCallRecord]:
        """
        Retrieve all tool call records for a conversation, ordered by created_at ASC.

        Args:
            conversation_id: The UUID of the conversation to retrieve tool calls for.

        Returns:
            list[ToolCallRecord]: A list of tool call records, or empty list if an error occurs.
        """
        try:
            result = await self.session.execute(
                select(ToolCallRecord)
                .filter(ToolCallRecord.conversation_id == conversation_id)
                .order_by(ToolCallRecord.created_at.asc())
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving tool call records: {e}")
            return []
