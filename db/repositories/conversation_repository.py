import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from db.tables import Conversation, ConversationStatus, Message
from utils.log import logger


class ConversationUpdate(BaseModel):
    """Model for updating conversation fields."""

    status: Optional[ConversationStatus] = None
    is_escalated: Optional[bool] = None
    project_id: Optional[uuid.UUID] = None


class ConversationRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_conversation_by_id(self, conversation_id: uuid.UUID):
        result = await self.session.execute(
            select(Conversation).filter(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"No conversation found with id {conversation_id}")

        return conversation

    async def get_open_conversations_by_user_id(
        self, user_id: uuid.UUID, limit: int = 5
    ):
        """
        Retrieve all active conversations for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user whose active conversations are being retrieved.

        Returns:
            list[Conversation]: A list of active conversation objects for the specified user.
        """
        result = await self.session.execute(
            select(Conversation)
            .filter(
                Conversation.user_id == user_id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .limit(limit)
        )
        return result.scalars().all()


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_conversations(self, skip: int = 0, limit: int = 100):
        """
        Retrieve a paginated list of conversations.

        Args:
            skip (int, optional): Number of records to skip. Defaults to 0.
            limit (int, optional): Maximum number of records to return. Defaults to 100.

        Returns:
            list[Conversation] | None: A list of conversation objects, or None if an error occurs.
        """
        try:
            return self.session.query(Conversation).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations: {e}")
            return None

    def get_conversations_by_user(self, user_id: uuid.UUID):
        """
        Retrieve all conversations for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user whose conversations are being retrieved.

        Returns:
            list[Conversation] | None: A list of conversation objects for the specified user, or None if an error occurs.

        Raises:
            ValueError: If 'user_id' is not provided.
        """
        if not user_id:
            raise ValueError("'user_id' must be provided")
        try:
            return (
                self.session.query(Conversation)
                .filter(Conversation.user_id == user_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations by user: {e}")
            return None

    def get_conversations_by_users(
        self,
        user_ids: list[uuid.UUID],
        page: int,
        page_size: int,
    ) -> tuple[list[Conversation], int]:
        """
        Retrieve conversations for a list of user IDs with pagination support.

        Args:
            user_ids (List[uuid.UUID]): A list of user IDs to filter conversations by.
            page (int): The current page number (default is 1).
            page_size (int): The number of items per page (default is 10).

        Returns:
            tuple[List[Conversation], int]: A tuple containing the list of conversations and the total count.
        """
        if not user_ids:
            # If no user ids are passed, return an empty list
            return [], 0

        try:
            # Base query without pagination for counting
            base_query = self.session.query(Conversation).filter(
                Conversation.user_id.in_(user_ids),
            )

            total_count = base_query.count()

            # Apply ordering and pagination
            conversations = (
                base_query.order_by(Conversation.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            return conversations, total_count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations by users: {e}")
            return [], 0

    def get_conversation_ids_by_user_ids(
        self,
        user_ids: list[uuid.UUID],
        start_date: datetime,
        end_date: datetime,
        project_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        try:
            query = self.session.query(Conversation.id).filter(
                Conversation.user_id.in_(user_ids),
                Conversation.created_at >= start_date,
                Conversation.created_at <= end_date,
            )

            if project_id is not None:
                query = query.filter(Conversation.project_id == project_id)

            return [id for (id,) in query.all()]
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversation ids: {e}")
            return []

    def get_conversation_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        try:
            return (
                self.session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversation by id: {e}")
            return None

    def create_conversation(self, user_id: uuid.UUID):
        """
        Create a new conversation for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user for whom the conversation is being created.

        Returns:
            Conversation | None: The created conversation object if successful, or None if an error occurs.
        """
        try:
            db_conversation = Conversation(user_id=user_id)
            self.session.add(db_conversation)
            self.session.commit()
            return db_conversation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating conversation: {e}")
            return None

    def get_session_count_by_user_and_status(
        self,
        user_ids: list[uuid.UUID],
        start_date: datetime,
        end_date: datetime,
        status: ConversationStatus | None = None,
    ) -> int:
        """
        Returns the count of sessions that belong to the given list of user ids
        and have the specified status, within the given date range.
        """
        try:
            query = self.session.query(Conversation).filter(
                Conversation.user_id.in_(user_ids),
                Conversation.created_at >= start_date,
                Conversation.created_at <= end_date,
            )
            if status:
                query = query.filter(Conversation.status == status)
            return query.count()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving session count: {e}")
            return 0

    def get_paginated_sessions_by_ids(
        self,
        session_ids: list[uuid.UUID],
        offset: int,
        limit: int,
    ) -> tuple[int, list[Conversation]]:
        """
        Retrieve a paginated list of Conversation sessions by their IDs.

        Args:
            session_ids (list[uuid.UUID]): A list of Conversation IDs to filter by.
            offset (int): The number of records to skip for pagination.
            limit (int): The maximum number of records to return.

        Returns:
            list[Conversation]: A list of Conversation objects matching the given IDs,
            ordered by creation date in descending order. Returns an empty list if an
            error occurs or no matching records are found.
        """
        try:
            base_query = (
                self.session.query(Conversation)
                .filter(
                    Conversation.id.in_(session_ids),
                )
                .order_by(Conversation.created_at.desc())
            )
            count = base_query.count()
            sessions = base_query.offset(offset).limit(limit).all()
            return count, sessions
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving sessions: {e}")
            return 0, []

    def get_conversion_data(self) -> list[dict]:
        """
        Get account ranking by checkout conversion rate (sync version).

        Returns:
            list[dict]: List of dictionaries containing conversion statistics for each account
        """
        try:
            conversion_analytics_query = """
            WITH account_stats AS (
                SELECT 
                    a.name as account_name,
                    COUNT(DISTINCT c.id) as total_conversations,
                    COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END) as conversations_with_orders,
                    COUNT(DISTINCT CASE WHEN o.status = 'paid' THEN c.id END) as conversations_with_paid_orders,
                    CASE 
                        WHEN COUNT(DISTINCT c.id) > 0 THEN 
                            ROUND((COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END)::DECIMAL / COUNT(DISTINCT c.id)::DECIMAL) * 100, 2)
                        ELSE 0 
                    END as checkout_conversion_rate,
                    CASE 
                        WHEN COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END) > 0 THEN 
                            ROUND((COUNT(DISTINCT CASE WHEN o.status = 'paid' THEN c.id END)::DECIMAL / COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END)::DECIMAL) * 100, 2)
                        ELSE 0 
                    END as paid_rate,
                    0 as is_total
                FROM accounts a
                INNER JOIN users u ON a.id = u.account_id
                INNER JOIN conversations c ON u.id = c.user_id
                LEFT JOIN orders o ON c.id = o.conversation_id
                WHERE a.status = 'active'
                GROUP BY a.id, a.name
                HAVING COUNT(DISTINCT c.id) >= 5

                UNION ALL

                SELECT 
                    'TOTAL' as account_name,
                    COUNT(DISTINCT c.id) as total_conversations,
                    COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END) as conversations_with_orders,
                    COUNT(DISTINCT CASE WHEN o.status = 'paid' THEN c.id END) as conversations_with_paid_orders,
                    CASE 
                        WHEN COUNT(DISTINCT c.id) > 0 THEN 
                            ROUND((COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END)::DECIMAL / COUNT(DISTINCT c.id)::DECIMAL) * 100, 2)
                        ELSE 0 
                    END as checkout_conversion_rate,
                    CASE 
                        WHEN COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END) > 0 THEN 
                            ROUND((COUNT(DISTINCT CASE WHEN o.status = 'paid' THEN c.id END)::DECIMAL / COUNT(DISTINCT CASE WHEN o.id IS NOT NULL THEN c.id END)::DECIMAL) * 100, 2)
                        ELSE 0 
                    END as paid_rate,
                    1 as is_total
                FROM accounts a
                INNER JOIN users u ON a.id = u.account_id
                INNER JOIN conversations c ON u.id = c.user_id
                LEFT JOIN orders o ON c.id = o.conversation_id
                WHERE a.status = 'active'
            )
            SELECT 
                account_name,
                total_conversations,
                conversations_with_orders,
                conversations_with_paid_orders,
                checkout_conversion_rate,
                paid_rate
            FROM account_stats
            ORDER BY 
                is_total,
                checkout_conversion_rate DESC, 
                total_conversations DESC;
            """

            result = self.session.execute(text(conversion_analytics_query))

            conversion_data = []
            for row in result:
                conversion_data.append(
                    {
                        "account_name": row.account_name,
                        "total_conversations": row.total_conversations,
                        "conversations_with_orders": row.conversations_with_orders,
                        "conversations_with_paid_orders": row.conversations_with_paid_orders,
                        "checkout_conversion_rate": float(row.checkout_conversion_rate),
                        "paid_rate": float(row.paid_rate),
                    }
                )

            return conversion_data

        except SQLAlchemyError as e:
            logger.error(f"Error getting conversion data: {e}")
            raise

    def update_conversation(
        self, conversation_id: uuid.UUID, update_data: ConversationUpdate
    ) -> Conversation | None:
        """
        Update a conversation with the given fields.

        Args:
            conversation_id (uuid.UUID): The ID of the conversation to update.
            update_data (ConversationUpdate): The fields to update and their new values.

        Returns:
            Conversation | None: The updated conversation if successful, None if the conversation doesn't exist.

        Raises:
            SQLAlchemyError: If there is an error updating the conversation.
        """
        try:
            conversation = self.get_conversation_by_id(conversation_id)
            if not conversation:
                return None

            if update_data.status is not None:
                conversation.status = update_data.status

            if update_data.project_id is not None:
                conversation.project_id = update_data.project_id

            if update_data.is_escalated is not None:
                self.session.query(Message).filter(
                    Message.conversation_id == conversation_id
                ).update(
                    {
                        Message.body: func.jsonb_set(
                            func.coalesce(Message.body, "{}"),
                            "{extras,escalated}",
                            func.to_jsonb(str(update_data.is_escalated).lower()),
                        )
                    },
                    synchronize_session=False,
                )

            self.session.commit()
            self.session.refresh(conversation)
            return conversation
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating conversation: {e}")
            raise
