from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.conversation import ConversationData
from db.tables.conversations import Conversation, ConversationStatus
from utils.log import logger


def _to_data(row: Conversation) -> ConversationData:
    """Convert an ORM Conversation to a ConversationData."""
    return ConversationData(
        id=row.id,
        user_id=row.user_id,
        status=row.status.value,
        is_test=row.is_test,
        created_at=row.created_at,
        project_id=row.project_id,
        channel=row.channel.value if row.channel else None,
        purpose=row.purpose,
        language=row.language,
        ended_reason=row.ended_reason,
        transfer_purpose=row.transfer_purpose,
        customer_converted=row.customer_converted,
        agent_fingerprint=row.agent_fingerprint,
        prompt_fingerprint=row.prompt_fingerprint,
        vapi_control_url=row.vapi_control_url,
        call_id=row.call_id,
        updated_at=row.updated_at,
    )


def _validate_limit(limit: int) -> None:
    """Raise ValueError if limit is out of range."""
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")


class ConversationRepository:
    """Async-only repository for Conversation records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, conversation_id: uuid.UUID) -> ConversationData | None:
        """Retrieve a conversation by ID."""
        try:
            result = await self.session.execute(
                select(Conversation).filter(Conversation.id == conversation_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving conversation by ID")
            raise

    async def get_by_call_id(self, call_id: str) -> ConversationData | None:
        """Retrieve a conversation by voice call ID.

        Returns the most recently created match because ``call_id`` does not
        have a unique constraint at the database level.
        """
        try:
            result = await self.session.execute(
                select(Conversation)
                .filter(Conversation.call_id == call_id)
                .order_by(Conversation.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving conversation by call_id")
            raise

    async def get_by_project(
        self, project_id: uuid.UUID, limit: int = 10
    ) -> list[ConversationData]:
        """Retrieve recent conversations for a project.

        Args:
            project_id: The project to query.
            limit: Number of records to return (1-1000, default 10).

        Raises:
            ValueError: If *limit* is out of range.
        """
        _validate_limit(limit)
        try:
            result = await self.session.execute(
                select(Conversation)
                .filter(Conversation.project_id == project_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving conversations by project")
            raise

    async def get_open_by_user_and_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, limit: int = 5
    ) -> list[ConversationData]:
        """Retrieve active conversations for a user and project.

        Args:
            user_id: The user to query.
            project_id: The project to query.
            limit: Number of records to return (1-1000, default 5).

        Raises:
            ValueError: If *limit* is out of range.
        """
        _validate_limit(limit)
        try:
            result = await self.session.execute(
                select(Conversation)
                .filter(
                    Conversation.user_id == user_id,
                    Conversation.project_id == project_id,
                    Conversation.status == ConversationStatus.ACTIVE,
                )
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving open conversations")
            raise
