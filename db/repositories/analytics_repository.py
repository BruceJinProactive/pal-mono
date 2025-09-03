import datetime
import uuid

from sqlalchemy import Float, case, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from db.tables import Account, Conversation, Message, Order, PhoneCall, Project, User
from utils.log import logger

# Turn threshold constants
LOW_TURN_THRESHOLD = 2  # Conversations with <= 2 turns are considered "low"
HIGH_TURN_THRESHOLD = 5  # Conversations with > 10 turns are considered "high"

# Call duration threshold constants (in seconds)
SHORT_CALL_THRESHOLD = 10.0  # Calls <= 10s are considered "short"
LONG_CALL_THRESHOLD = 120.0  # Calls > 120s are considered "long"


class AnalyticsRepository:
    def __init__(self, session: Session):
        self.session = session

    def _build_group_fields(self, group_by: list[str] | None) -> tuple[list, list]:
        """
        Build select and group fields based on group_by parameter.

        Returns:
            tuple: (select_fields, group_fields)
        """
        select_fields = []
        group_fields = []

        if group_by:
            for field in group_by:
                if field == "account_id":
                    select_fields.append(User.account_id.label("account_id"))
                    select_fields.append(Account.name.label("account_name"))
                    group_fields.append(User.account_id)
                    group_fields.append(Account.name)
                elif field == "project_id":
                    select_fields.append(Conversation.project_id.label("project_id"))
                    select_fields.append(Project.name.label("project_name"))
                    group_fields.append(Conversation.project_id)
                    group_fields.append(Project.name)
                elif field == "date":
                    date_field = func.date(Conversation.created_at).label("date")
                    select_fields.append(date_field)
                    group_fields.append(date_field)

        return select_fields, group_fields

    def _apply_filters(
        self, query, filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None
    ):
        """
        Apply optional filters to the query.

        Args:
            query: SQLAlchemy query object
            filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

        Returns:
            Modified query with filters applied
        """
        if not filter_by:
            return query

        logger.info(f"Analytics: Applying filters: {filter_by}")
        conditions = []
        if "account_id" in filter_by:
            account_filter = filter_by["account_id"]
            logger.info(
                f"Analytics: Account filter - type: {type(account_filter)}, value: {account_filter}"
            )
            if isinstance(account_filter, list):
                conditions.append(User.account_id.in_(account_filter))
            else:
                conditions.append(User.account_id == account_filter)
        if "project_id" in filter_by:
            project_filter = filter_by["project_id"]
            logger.info(
                f"Analytics: Project filter - type: {type(project_filter)}, value: {project_filter}"
            )
            if isinstance(project_filter, list):
                conditions.append(Conversation.project_id.in_(project_filter))
            else:
                conditions.append(Conversation.project_id == project_filter)

        if conditions:
            logger.info(
                f"Analytics: Adding {len(conditions)} filter conditions to query"
            )
            query = query.where(*conditions)

        return query

    def get_active_users(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple]:
        """
        Get active users grouped by multiple dimensions.

        Note: Uses conversation creation as the measure of user activity, which is more
        accurate than message-based activity since users are active when they start conversations.

        Args:
            start_date: Start date for filtering conversations
            end_date: End date for filtering conversations
            group_by: List of fields to group by ['account_id', 'project_id', 'date']
            filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]} (no date filtering)

        Returns:
            list[tuple]: (group_field1, group_field2, ..., active_users, conversations)
        """
        try:
            select_fields, group_fields = self._build_group_fields(group_by)

            # Add aggregation fields
            select_fields.extend(
                [
                    func.count(func.distinct(Conversation.user_id)).label(
                        "active_users"
                    ),
                    func.count(Conversation.id).label("conversations"),
                ]
            )

            # Build the query - using Conversation as primary table
            query = (
                select(*select_fields)
                .select_from(Conversation)
                .join(User, Conversation.user_id == User.id)
            )

            # Add Account join if needed for grouping
            if group_by and "account_id" in group_by:
                query = query.join(Account, User.account_id == Account.id)

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            query = query.where(
                Conversation.created_at.between(start_date, end_date),
            )

            # Apply optional filters
            query = self._apply_filters(query, filter_by)

            # Apply grouping and ordering
            if group_fields:
                query = query.group_by(*group_fields).order_by(
                    func.count(func.distinct(Conversation.user_id)).desc()
                )
            else:
                query = query.order_by(
                    func.count(func.distinct(Conversation.user_id)).desc()
                )

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]
            logger.info(
                f"Analytics: Active users query returned {len(rows)} rows: {rows}"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting grouped active users by {group_by}: {e}")
            return []
        except ValueError as e:
            logger.error(f"Invalid group_by parameter: {e}")
            return []

    def get_turns_summary(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple]:
        """
        Get turn distribution metrics.


        """
        try:
            select_fields, group_fields = self._build_group_fields(group_by)

            # First, get conversations in the date range
            valid_conversations = (
                select(Conversation.id)
                .select_from(Conversation)
                .where(
                    Conversation.created_at.between(start_date, end_date),
                )
                .subquery()
            )

            # Then calculate turns for those conversations
            # Calculate turns as number of agent messages in the conversation
            conversation_turns = (
                select(
                    Conversation.id,
                    func.coalesce(
                        func.sum(
                            case(
                                (Message.body["author_type"].astext == "agent", 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("turns"),
                )
                .select_from(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(Conversation.id.in_(select(valid_conversations.c.id)))
                .group_by(Conversation.id)
                .subquery()
            )

            # Main query with metrics - need to join back to get grouping fields
            select_fields.extend(
                [
                    func.sum(
                        case(
                            (conversation_turns.c.turns <= LOW_TURN_THRESHOLD, 1),
                            else_=0,
                        )
                    ).label("low_turns"),
                    func.sum(
                        case(
                            (conversation_turns.c.turns > HIGH_TURN_THRESHOLD, 1),
                            else_=0,
                        )
                    ).label("high_turns"),
                    func.count(conversation_turns.c.id).label("total_convs"),
                    func.sum(conversation_turns.c.turns).label("total_turns"),
                ]
            )

            query = (
                select(*select_fields)
                .select_from(conversation_turns)
                .join(Conversation, conversation_turns.c.id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
            )

            # Add Account join if needed for grouping
            if group_by and "account_id" in group_by:
                query = query.join(Account, User.account_id == Account.id)

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Apply optional filters
            query = self._apply_filters(query, filter_by)

            # Apply grouping
            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]
            logger.info(
                f"Analytics: Turn distribution query returned {len(rows)} rows: {rows}"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting turn distribution: {e}")
            return []

    def get_calls_time_summary(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple]:
        """
        Get essential call metrics following the same pattern as get_turns_summary.

        Returns:
            list[tuple]: (group_fields...,
                         total_calls, avg_duration, avg_turn_latency,
                         short_calls, long_calls,
                         transfer_calls, transfer_rate,
                         positive_calls, neutral_calls, negative_calls)
        """
        try:
            from db.tables import PhoneCall

            select_fields, group_fields = self._build_group_fields(group_by)

            select_fields.extend(
                [
                    # Basic metrics
                    func.count(PhoneCall.id).label("total_calls"),
                    func.avg(PhoneCall.duration).label("avg_duration"),
                    func.avg(PhoneCall.turn_latency_avg).label("avg_turn_latency"),
                    # Duration distribution
                    func.sum(
                        case(
                            (PhoneCall.duration <= SHORT_CALL_THRESHOLD, 1),
                            else_=0,
                        )
                    ).label("short_calls"),
                    func.sum(
                        case(
                            (PhoneCall.duration > LONG_CALL_THRESHOLD, 1),
                            else_=0,
                        )
                    ).label("long_calls"),
                    # Transfer metrics
                    func.sum(
                        case(
                            (PhoneCall.ended_reason == "assistant_forwarded", 1),
                            else_=0,
                        )
                    ).label("transfer_calls"),
                    (
                        func.sum(
                            case(
                                (PhoneCall.ended_reason == "assistant_forwarded", 1),
                                else_=0,
                            )
                        ).cast(Float)
                        / func.count(PhoneCall.id)
                        * 100
                    ).label("transfer_rate"),
                    # Satisfaction counts
                    func.sum(
                        case(
                            (PhoneCall.user_satisfaction == "positive", 1),
                            else_=0,
                        )
                    ).label("positive_calls"),
                    func.sum(
                        case(
                            (PhoneCall.user_satisfaction == "neutral", 1),
                            else_=0,
                        )
                    ).label("neutral_calls"),
                    func.sum(
                        case(
                            (PhoneCall.user_satisfaction == "negative", 1),
                            else_=0,
                        )
                    ).label("negative_calls"),
                ]
            )

            # Build query - join PhoneCall -> Conversation -> User (same pattern as turns)
            query = (
                select(*select_fields)
                .select_from(PhoneCall)
                .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
            )

            # Add Account join if needed for grouping
            if group_by and "account_id" in group_by:
                query = query.join(Account, User.account_id == Account.id)

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Filter by call creation date
            query = query.where(PhoneCall.created_at.between(start_date, end_date))

            # Apply optional filters (reuse existing logic)
            query = self._apply_filters(query, filter_by)

            # Apply grouping
            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]
            logger.info(
                f"Analytics: Call time summary query returned {len(rows)} rows: {rows}"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting call time summary: {e}")
            return []

    def get_calls_info_summary(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple]:
        """
        Get call purpose and language distribution in a single query.
        Service layer handles date filtering for overall distributions.

        Returns:
            list[tuple]: Combined purpose and language distribution data
        """
        try:
            from db.tables.types import CallLanguage, CallPurpose

            # Build group fields normally (service layer handles date filtering)
            select_fields, group_fields = self._build_group_fields(group_by)

            # Get all possible enum values dynamically
            all_purposes = [purpose.value for purpose in CallPurpose]
            all_languages = [language.value for language in CallLanguage]

            # Build combined select fields with both purposes and languages
            combined_select_fields = select_fields.copy()

            # Add purpose distribution fields
            for purpose in all_purposes:
                purpose_count = func.sum(
                    case(
                        (
                            func.array_to_string(PhoneCall.call_purpose, ",").contains(
                                purpose
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label(purpose)
                combined_select_fields.append(purpose_count)

            # Add language distribution fields
            for language in all_languages:
                language_count = func.sum(
                    case(
                        (PhoneCall.language == language, 1),
                        else_=0,
                    )
                ).label(language)
                combined_select_fields.append(language_count)

            # Build single query with all fields
            query = (
                select(*combined_select_fields)
                .select_from(PhoneCall)
                .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
            )

            # Add joins for grouping
            if group_by and "account_id" in group_by:
                query = query.join(Account, User.account_id == Account.id)
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Apply filters
            query = query.where(PhoneCall.created_at.between(start_date, end_date))
            query = self._apply_filters(query, filter_by)

            # Group by if needed
            if group_fields:
                query = query.group_by(*group_fields)

            # Execute single query
            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            logger.info(
                f"Analytics: Call info summary query returned {len(rows)} rows with {len(all_purposes)} purposes and {len(all_languages)} languages"
            )

            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting call info summary: {e}")
            return []

    def get_conversion_summary(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple]:
        """
        Get conversion metrics showing how many conversations lead to orders and paid orders.

        Returns:
            list[tuple]: (group_fields...,
                         total_conversations, conversations_with_orders,
                         paid_orders, total_subtotal, paid_total)
        """
        try:
            select_fields, group_fields = self._build_group_fields(group_by)

            select_fields.extend(
                [
                    # Total conversations in the date range
                    func.count(Conversation.id).label("total_conversations"),
                    # Conversations that have orders (any status)
                    func.count(
                        case(
                            (Order.id.isnot(None), Conversation.id),
                            else_=None,
                        )
                    ).label("conversations_with_orders"),
                    # Orders with paid status
                    func.count(
                        case(
                            (Order.status == "paid", Order.id),
                            else_=None,
                        )
                    ).label("paid_orders"),
                    # Total subtotal (monetary value) from all orders
                    func.coalesce(func.sum(Order.subtotal), 0).label("total_subtotal"),
                    # Paid total (monetary value) from only paid orders
                    func.coalesce(
                        func.sum(
                            case(
                                (Order.status == "paid", Order.subtotal),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("paid_total"),
                ]
            )

            # Build query - join Conversation -> Order (left join to include conversations without orders)
            query = (
                select(*select_fields)
                .select_from(Conversation)
                .join(User, Conversation.user_id == User.id)
                .outerjoin(Order, Conversation.id == Order.conversation_id)
            )

            # Add Account join if needed for grouping
            if group_by and "account_id" in group_by:
                query = query.join(Account, User.account_id == Account.id)

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Filter by conversation creation date
            query = query.where(Conversation.created_at.between(start_date, end_date))

            # Apply optional filters
            query = self._apply_filters(query, filter_by)

            # Apply grouping
            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]
            logger.info(
                f"Analytics: Conversion summary query returned {len(rows)} rows: {rows}"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting conversion summary: {e}")
            return []
