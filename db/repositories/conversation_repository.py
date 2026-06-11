import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import Text, cast, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from db.tables import (
    Account,
    CallPurpose,
    Conversation,
    ConversationStatus,
    Message,
    Order,
    User,
)
from utils.log import logger

OrderFilter = Literal["all", "paid", "unpaid"]

_INVALID_DISPLAY_ORDER_NUMBERS = ("", "0", "none", "null", "n/a", "na", "unknown")


def _split_call_purpose_values(raw_purposes: list[str]) -> list[str]:
    """Return unique first-level purpose tokens from raw comma-separated values."""
    purpose_values: list[str] = []
    seen_values: set[str] = set()

    for raw_purpose in raw_purposes:
        for purpose in raw_purpose.split(","):
            stripped_purpose = purpose.strip()
            if not stripped_purpose or stripped_purpose in seen_values:
                continue
            seen_values.add(stripped_purpose)
            purpose_values.append(stripped_purpose)

    return purpose_values


def _normalize_call_purpose_filter_values(raw_purposes: list[str]) -> list[str]:
    """Return known first-level call purpose values in enum order."""
    present_purposes = set(_split_call_purpose_values(raw_purposes))
    return [
        call_purpose.value
        for call_purpose in CallPurpose
        if call_purpose.value in present_purposes
    ]


def _latest_order_for_conversation_subquery() -> Subquery:
    sort_time = func.coalesce(Order.order_time, Order.created_at)
    return select(
        Order.conversation_id.label("conversation_id"),
        Order.order_id.label("order_id"),
        func.row_number()
        .over(
            partition_by=Order.conversation_id,
            order_by=(sort_time.desc(), Order.created_at.desc()),
        )
        .label("order_rank"),
    ).subquery()


def _has_display_order_number(
    order_id_column: ColumnElement[Any],
) -> ColumnElement[bool]:
    normalized_order_id = func.lower(func.trim(func.coalesce(order_id_column, "")))
    return normalized_order_id.notin_(_INVALID_DISPLAY_ORDER_NUMBERS)


class ConversationUpdate(BaseModel):
    """Model for updating conversation fields."""

    status: Optional[ConversationStatus] = None
    is_escalated: Optional[bool] = None
    project_id: Optional[uuid.UUID] = None
    vapi_control_url: Optional[str] = None
    purpose: Optional[str] = None
    language: Optional[str] = None
    ended_reason: Optional[str] = None
    customer_converted: Optional[uuid.UUID] = None


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

    async def get_conversation_by_call_id(self, call_id: str) -> Conversation | None:
        """
        Retrieve a conversation by its voice call ID.

        Args:
            call_id: The voice call ID associated with the conversation.

        Returns:
            Conversation | None: The conversation if found, None otherwise.
        """
        try:
            result = await self.session.execute(
                select(Conversation).filter(Conversation.call_id == call_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving conversation by call_id: {e}")
            return None

    async def get_open_conversations_by_user_and_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, limit: int = 5
    ):
        """
        Retrieve all active conversations for a specific user and project.

        Args:
            user_id (uuid.UUID): The ID of the user whose active conversations are being retrieved.
            project_id (uuid.UUID): The ID of the project to filter conversations by.

        Returns:
            list[Conversation]: A list of active conversation objects for the specified user and project.
        """
        result = await self.session.execute(
            select(Conversation)
            .filter(
                Conversation.user_id == user_id,
                Conversation.project_id == project_id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_project(
        self, project_id: uuid.UUID, limit: int = 10
    ) -> list[Conversation]:
        """Retrieve recent conversations for a project, ordered by created_at DESC."""
        try:
            result = await self.session.execute(
                select(Conversation)
                .filter(Conversation.project_id == project_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error retrieving conversations by project: {e}")
            return []

    async def count_conversations_by_account_id(self, account_id: uuid.UUID) -> int:
        """
        Count the total number of conversations for a given account id.

        Args:
            account_id (uuid.UUID): The ID of the account.

        Returns:
            int: The total number of conversations for the account.
        """
        try:
            result = await self.session.execute(
                select(func.count(func.distinct(Conversation.id)))
                .join(User, Conversation.user_id == User.id)
                .filter(User.account_id == account_id)
            )
            return result.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"Error counting conversations by account id: {e}")
            raise

    async def atomic_close_conversation(
        self, conversation_id: uuid.UUID, update_data: ConversationUpdate
    ) -> bool:
        """
        Atomically close a conversation only if it's not already closed.
        This prevents race conditions where multiple processes try to close the same conversation.

        Args:
            conversation_id (uuid.UUID): The ID of the conversation to close.
            update_data (ConversationUpdate): The fields to update (must include status=CLOSED).

        Returns:
            bool: True if the conversation was successfully closed by this call,
                  False if it was already closed or doesn't exist.

        Raises:
            SQLAlchemyError: If there is an error updating the conversation.
        """
        try:
            # Build update values dict from update_data
            values = {}
            if update_data.status is not None:
                values["status"] = update_data.status
            if update_data.purpose is not None:
                values["purpose"] = update_data.purpose
            if update_data.language is not None:
                values["language"] = update_data.language
            if update_data.ended_reason is not None:
                values["ended_reason"] = update_data.ended_reason
            if update_data.customer_converted is not None:
                values["customer_converted"] = update_data.customer_converted

            # Atomic update: only update if status is NOT already CLOSED
            result = await self.session.execute(
                update(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.status != ConversationStatus.CLOSED,
                )
                .values(**values)
            )

            # Handle is_escalated separately if needed
            if update_data.is_escalated is not None:
                await self.session.execute(
                    update(Message)
                    .where(Message.conversation_id == conversation_id)
                    .values(
                        body=func.jsonb_set(
                            func.coalesce(Message.body, "{}"),
                            "{extras,escalated}",
                            func.to_jsonb(str(update_data.is_escalated).lower()),
                        )
                    )
                )

            await self.session.commit()

            # Return True only if we updated exactly one row (won the race)
            return result.rowcount == 1

        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error atomically closing conversation: {e}")
            raise

    async def update_conversation(
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
            conversation = await self.get_conversation_by_id(conversation_id)
            if not conversation:
                return None

            if update_data.status is not None:
                conversation.status = update_data.status

            if update_data.project_id is not None:
                conversation.project_id = update_data.project_id

            if update_data.vapi_control_url is not None:
                conversation.vapi_control_url = update_data.vapi_control_url

            if update_data.purpose is not None:
                conversation.purpose = update_data.purpose

            if update_data.language is not None:
                conversation.language = update_data.language

            if update_data.ended_reason is not None:
                conversation.ended_reason = update_data.ended_reason

            if update_data.customer_converted is not None:
                conversation.customer_converted = update_data.customer_converted

            if update_data.is_escalated is not None:
                await self.session.execute(
                    update(Message)
                    .where(Message.conversation_id == conversation_id)
                    .values(
                        body=func.jsonb_set(
                            func.coalesce(Message.body, "{}"),
                            "{extras,escalated}",
                            func.to_jsonb(str(update_data.is_escalated).lower()),
                        )
                    )
                )

            await self.session.commit()
            await self.session.refresh(conversation)
            return conversation
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating conversation: {e}")
            raise


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
            list[Conversation]: A list of conversation objects, or empty list if an error occurs.
        """
        try:
            return self.session.query(Conversation).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving conversations: {e}")
            return []

    def get_conversations_by_user(self, user_id: uuid.UUID):
        """
        Retrieve all conversations for a specific user.

        Args:
            user_id (uuid.UUID): The ID of the user whose conversations are being retrieved.

        Returns:
            list[Conversation]: A list of conversation objects for the specified user, or empty list if an error occurs.

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
            return []

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
        start_date: datetime | None,
        end_date: datetime,
        project_id: uuid.UUID | None = None,
        hide_testing_sessions: bool = False,
        language: list[str] | None = None,
        purpose: list[str] | None = None,
        ended_reason: list[str] | None = None,
        customer_converted: bool | None = None,
        has_order: bool | None = None,
        order_filter: OrderFilter | None = None,
    ) -> list[uuid.UUID]:
        try:
            query = self.session.query(Conversation.id).filter(
                Conversation.user_id.in_(user_ids),
                Conversation.created_at <= end_date,
            )

            if start_date:
                query = query.filter(Conversation.created_at >= start_date)
            if project_id is not None:
                query = query.filter(Conversation.project_id == project_id)
            if hide_testing_sessions:
                query = query.filter(Conversation.is_test.is_not(True))
            if language is not None and len(language) > 0:
                query = query.filter(Conversation.language.in_(language))
            if purpose is not None and len(purpose) > 0:
                purpose_values = _split_call_purpose_values(purpose)
                if purpose_values:
                    query = query.filter(
                        func.string_to_array(Conversation.purpose, ",").op("&&")(
                            cast(purpose_values, ARRAY(Text))
                        )
                    )
            if ended_reason is not None and len(ended_reason) > 0:
                query = query.filter(Conversation.ended_reason.in_(ended_reason))
            if customer_converted is not None:
                if customer_converted:
                    query = query.filter(Conversation.customer_converted.is_not(None))
                else:
                    query = query.filter(Conversation.customer_converted.is_(None))
            if order_filter == "all":
                query = query.filter(Conversation.id.in_(select(Order.conversation_id)))
            elif order_filter in {"paid", "unpaid"}:
                latest_order = _latest_order_for_conversation_subquery()
                query = query.join(
                    latest_order,
                    (latest_order.c.conversation_id == Conversation.id)
                    & (latest_order.c.order_rank == 1),
                )
                if order_filter == "paid":
                    query = query.filter(
                        _has_display_order_number(latest_order.c.order_id)
                    )
                else:
                    query = query.filter(
                        ~_has_display_order_number(latest_order.c.order_id)
                    )
            elif order_filter is not None:
                raise ValueError(f"Unsupported order filter: {order_filter}")
            elif has_order is not None:
                order_conversation_ids = select(Order.conversation_id)
                if has_order:
                    query = query.filter(Conversation.id.in_(order_conversation_ids))
                else:
                    query = query.filter(Conversation.id.notin_(order_conversation_ids))

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

    def get_distinct_filter_values(
        self, account_id: uuid.UUID
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Get distinct values for language, purpose, and ended_reason fields
        for conversations belonging to an account.

        Uses a single query with array_agg to reduce database round trips.

        Returns:
            tuple: (languages, purposes, ended_reasons)
        """
        try:
            # Use array_agg with distinct to get all values in a single query
            # This reduces 3 database round trips to 1
            result = (
                self.session.query(
                    func.array_agg(func.distinct(Conversation.language)).filter(
                        Conversation.language.is_not(None)
                    ),
                    func.array_agg(func.distinct(Conversation.purpose)).filter(
                        Conversation.purpose.is_not(None)
                    ),
                    func.array_agg(func.distinct(Conversation.ended_reason)).filter(
                        Conversation.ended_reason.is_not(None)
                    ),
                )
                .join(User, Conversation.user_id == User.id)
                .filter(User.account_id == account_id)
                .one()
            )

            # array_agg returns None if no rows match, convert to empty list
            languages = result[0] or []
            purposes = _normalize_call_purpose_filter_values(result[1] or [])
            ended_reasons = result[2] or []

            return (languages, purposes, ended_reasons)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving distinct filter values: {e}")
            return [], [], []

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

            if update_data.vapi_control_url is not None:
                conversation.vapi_control_url = update_data.vapi_control_url

            if update_data.purpose is not None:
                conversation.purpose = update_data.purpose

            if update_data.language is not None:
                conversation.language = update_data.language

            if update_data.ended_reason is not None:
                conversation.ended_reason = update_data.ended_reason

            if update_data.customer_converted is not None:
                conversation.customer_converted = update_data.customer_converted

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

    def get_conversation_counts_by_account(
        self,
        account_id: uuid.UUID | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[tuple[uuid.UUID | None, str, int]]:
        """
        Get conversation counts grouped by account with optional date filtering.
        Always includes a TOTAL row with aggregated data.

        Args:
            account_id: Optional account ID. If provided, gets data for single account.
                       If None, gets data for all accounts.
            start_date: Optional start date for filtering conversations. If None, no start limit.
            end_date: Optional end date for filtering conversations. If None, no end limit.

        Returns:
            list[tuple[uuid.UUID | None, str, int]]: List of tuples (account_id, account_name, total_conversations)
                        Last row will always be (None, 'TOTAL', sum_total)
        """
        try:
            query = (
                self.session.query(
                    Account.id,
                    Account.name,
                    func.count(func.distinct(Conversation.id)),
                )
                .join(User, Account.id == User.account_id)
                .join(Conversation, User.id == Conversation.user_id)
            )

            # Add date filtering if provided
            if start_date is not None:
                query = query.filter(Conversation.created_at >= start_date)
            if end_date is not None:
                query = query.filter(Conversation.created_at <= end_date)

            if account_id is not None:
                # Single account query
                query = query.filter(Account.id == account_id)
                query = query.group_by(Account.id, Account.name)
                results = query.all()
                # Convert Row objects to tuples
                return [(row[0], row[1], row[2]) for row in results]
            else:
                # All accounts query - only include accounts with at least 5 conversations
                query = query.having(func.count(func.distinct(Conversation.id)) >= 5)
                query = query.group_by(Account.id, Account.name)

                results = query.all()

                # Convert Row objects to tuples
                tuple_results = [(row[0], row[1], row[2]) for row in results]

                # Always add total row
                if tuple_results:
                    total_conversations = sum(row[2] for row in tuple_results)
                    tuple_results.append((None, "TOTAL", total_conversations))

                return tuple_results

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting conversation counts by account: {e}")
            raise
