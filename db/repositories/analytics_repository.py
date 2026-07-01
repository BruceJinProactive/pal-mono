import datetime
import time
import uuid
from typing import Any, Literal, cast

from sqlalchemy import Float, and_, case, exists, func, not_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from db.tables import (
    Account,
    Agent,
    AgentCapability,
    Contact,
    Conversation,
    Integration,
    Message,
    Order,
    PhoneCall,
    Project,
    ProjectContact,
    ProjectIntegration,
    Reservation,
    ToastCheckoutSession,
    ToolCallRecord,
    User,
)
from db.tables.types import CallEndedReason, IntegrationProvider, IntegrationType
from utils.log import logger

# Turn threshold constants
LOW_TURN_THRESHOLD = 2  # Conversations with <= 2 turns are considered "low"
HIGH_TURN_THRESHOLD = 5  # Conversations with > 10 turns are considered "high"

# Call duration threshold constants (in seconds)
SHORT_CALL_THRESHOLD = 10.0  # Calls <= 10s are considered "short"
LONG_CALL_THRESHOLD = 120.0  # Calls > 120s are considered "long"

ORDERING_CAPABILITY_IDENTIFIER = "ordering"
ORDERING_TOOL_NAMES = (
    "adora_tool",
    "adora_v2_tool",
    "adora_v3",
    "menusifu_tool",
    "olo_tool",
    "square_tool",
    "toast_tool",
    "toast_v3",
)

CallInsightsRow = tuple[
    str,
    uuid.UUID,
    datetime.datetime,
    float | None,
    CallEndedReason | str | None,
    str | None,
    bool | None,
    str | None,
    uuid.UUID,
    list[str] | None,
    uuid.UUID,
    str,
    uuid.UUID | None,
    str | None,
    str | None,
    dict[str, Any] | None,
    str | None,
    str | None,
    datetime.datetime | None,
    int,
]


class AnalyticsRepository:
    def __init__(self, session: Session):
        self.session = session

    def _project_filter_conditions(self, project_ids: list[uuid.UUID] | None) -> list:
        """Build reusable project filter conditions."""
        if not project_ids:
            return []
        return [Project.id.in_(project_ids)]

    def has_ordering_enabled(
        self,
        account_id: uuid.UUID,
        project_ids: list[uuid.UUID] | None = None,
    ) -> bool:
        """
        Return whether ordering is enabled for an account/project scope.

        Checks the explicit ordering capability, ProjectIntegration tool names used by
        the new agent stack, and legacy agent/project raw_config tool identifiers.
        """
        try:
            project_conditions = self._project_filter_conditions(project_ids)

            capability_query = (
                select(AgentCapability.id)
                .select_from(AgentCapability)
                .join(Agent, AgentCapability.agent_id == Agent.id)
                .join(Project, Project.agent_id == Agent.id)
                .where(
                    Agent.account_id == account_id,
                    Project.account_id == account_id,
                    AgentCapability.capability_identifier
                    == ORDERING_CAPABILITY_IDENTIFIER,
                    AgentCapability.enabled.is_(True),
                    *project_conditions,
                )
                .limit(1)
            )
            if self.session.execute(capability_query).first() is not None:
                return True

            project_integration_query = (
                select(ProjectIntegration.id)
                .select_from(ProjectIntegration)
                .join(Project, ProjectIntegration.project_id == Project.id)
                .where(
                    Project.account_id == account_id,
                    ProjectIntegration.tool_name.in_(ORDERING_TOOL_NAMES),
                    *project_conditions,
                )
                .limit(1)
            )
            if self.session.execute(project_integration_query).first() is not None:
                return True

            raw_config_conditions = []
            for tool_name in ORDERING_TOOL_NAMES:
                tool_identifier = {"tools": {"identifiers": [{"tool_name": tool_name}]}}
                raw_config_conditions.append(
                    Project.raw_config.contains(tool_identifier)
                )
                raw_config_conditions.append(Agent.raw_config.contains(tool_identifier))

            raw_config_query = (
                select(Project.id)
                .select_from(Project)
                .join(Agent, Project.agent_id == Agent.id)
                .where(
                    Project.account_id == account_id,
                    Agent.account_id == account_id,
                    or_(*raw_config_conditions),
                    *project_conditions,
                )
                .limit(1)
            )
            return self.session.execute(raw_config_query).first() is not None

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error checking ordering capability: {e}")
            return False

    def get_order_accuracy_time_series(
        self,
        account_id: uuid.UUID,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        project_ids: list[uuid.UUID] | None = None,
    ) -> list[tuple]:
        """
        Get daily order-call accuracy metrics for dashboard charts.

        Accuracy is measured per distinct conversation with one or more orders:
        conversations with orders and no ToolCallRecord.is_error are accurate.
        """
        try:
            start_time = time.time()
            conversation_date = func.date(Conversation.created_at).label("date")
            conditions = [
                User.account_id == account_id,
                Conversation.created_at.between(start_date, end_date),
                ~Conversation.is_test,
                exists(
                    select(1)
                    .select_from(Integration)
                    .where(
                        Integration.account_id == User.account_id,
                        or_(
                            Integration.integration_type == IntegrationType.pos,
                            Integration.integration_type == IntegrationType.reservation,
                        ),
                    )
                ),
            ]
            if project_ids:
                conditions.append(Conversation.project_id.in_(project_ids))

            tool_errors = (
                select(
                    ToolCallRecord.conversation_id.label("conversation_id"),
                    func.bool_or(ToolCallRecord.is_error).label("has_tool_error"),
                )
                .group_by(ToolCallRecord.conversation_id)
                .subquery()
            )

            order_conversations = (
                select(
                    conversation_date,
                    Conversation.id.label("conversation_id"),
                    func.coalesce(tool_errors.c.has_tool_error, False).label(
                        "has_tool_error"
                    ),
                )
                .select_from(Conversation)
                .join(User, Conversation.user_id == User.id)
                .join(Order, Conversation.id == Order.conversation_id)
                .outerjoin(
                    tool_errors, Conversation.id == tool_errors.c.conversation_id
                )
                .where(
                    *conditions,
                )
                .group_by(
                    conversation_date, Conversation.id, tool_errors.c.has_tool_error
                )
                .subquery()
            )

            query = select(
                order_conversations.c.date,
                func.count(order_conversations.c.conversation_id).label(
                    "order_call_count"
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                order_conversations.c.has_tool_error.is_(False),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("accurate_order_call_count"),
            ).select_from(order_conversations)

            query = query.group_by(order_conversations.c.date).order_by(
                order_conversations.c.date
            )

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            elapsed = time.time() - start_time
            logger.info(
                "AnalyticsRepository: Order accuracy query executed in "
                f"{elapsed:.3f}s, returned {len(rows)} rows"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting order accuracy metrics: {e}")
            return []

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

        conditions = []
        if "account_id" in filter_by:
            account_filter = filter_by["account_id"]
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
            start_time = time.time()
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

            # Build the query with early filtering optimization
            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]

                # Handle both single UUID and list of UUIDs
                if isinstance(account_filter, list):
                    account_condition = User.account_id.in_(account_filter)
                else:
                    account_condition = User.account_id == account_filter

                query = (
                    select(*select_fields)
                    .select_from(Conversation)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        Conversation.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                        account_condition,
                    )
                )
            else:
                query = (
                    select(*select_fields)
                    .select_from(Conversation)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        Conversation.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                    )
                )

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Apply project_id filter early if present
            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

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

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyticsRepository: Active users query executed in {elapsed:.3f}s, returned {len(rows)} rows"
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
        OPTIMIZED: Filters early and avoids scanning all messages.
        """
        try:
            start_time = time.time()
            select_fields, group_fields = self._build_group_fields(group_by)

            # OPTIMIZED: Build all filter conditions upfront
            base_conditions = [
                Conversation.created_at.between(start_date, end_date),
                ~Conversation.is_test,
            ]

            # Add account filter early
            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]
                if isinstance(account_filter, list):
                    base_conditions.append(User.account_id.in_(account_filter))
                else:
                    base_conditions.append(User.account_id == account_filter)

            # CRITICAL OPTIMIZATION: Add project filter early (was applied too late before)
            if filter_by and "project_id" in filter_by:
                project_filter = filter_by["project_id"]
                if isinstance(project_filter, list):
                    base_conditions.append(Conversation.project_id.in_(project_filter))
                else:
                    base_conditions.append(Conversation.project_id == project_filter)

            # OPTIMIZED: Single query that starts with filtered conversations
            # and only processes messages from those conversations (not ALL messages)
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
                .select_from(Conversation)
                .join(User, Conversation.user_id == User.id)
                .join(Account, User.account_id == Account.id)
                .outerjoin(
                    Message, Message.conversation_id == Conversation.id
                )  # LEFT JOIN to include conversations with no messages
                .where(*base_conditions)
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

            # Apply project_id filter early if present
            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

            # Apply grouping
            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyticsRepository: Turns summary query executed in {elapsed:.3f}s, returned {len(rows)} rows"
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
        exclude_eval_calls: bool = False,
        exclude_caller_numbers: list[str] | None = None,
    ) -> list[tuple]:
        """
        Get essential call metrics following the same pattern as get_turns_summary.

        Args:
            start_date: Start date for filtering
            end_date: End date for filtering
            group_by: List of fields to group by
            filter_by: Dict of filters
            exclude_eval_calls: If True, exclude calls with call_id starting with 'eval-'
            exclude_caller_numbers: List of phone numbers to exclude (test numbers)

        Returns:
            list[tuple]: (group_fields...,
                         total_calls, avg_duration, avg_turn_latency,
                         short_calls, long_calls,
                         transfer_calls, transfer_rate,
                         positive_calls, neutral_calls, negative_calls)
        """
        try:
            start_time = time.time()
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

            # Build query with early filtering optimization
            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]

                # Handle both single UUID and list of UUIDs
                if isinstance(account_filter, list):
                    account_condition = User.account_id.in_(account_filter)
                else:
                    account_condition = User.account_id == account_filter

                query = (
                    select(*select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                        account_condition,
                    )
                )
            else:
                query = (
                    select(*select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                    )
                )

            # Exclude eval pipeline calls (call_id starts with 'eval-')
            if exclude_eval_calls:
                query = query.where(
                    not_(Conversation.call_id.like("eval-%"))
                    | Conversation.call_id.is_(None)
                )

            # Exclude calls from test phone numbers
            if exclude_caller_numbers:
                query = query.where(
                    ~User.channel_identifiers.overlap(exclude_caller_numbers)
                )

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Apply project_id filter early if present
            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

            # Apply grouping
            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyticsRepository: Call time summary query executed in {elapsed:.3f}s, returned {len(rows)} rows"
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

            # Build single query with early filtering optimization
            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]

                # Handle both single UUID and list of UUIDs
                if isinstance(account_filter, list):
                    account_condition = User.account_id.in_(account_filter)
                else:
                    account_condition = User.account_id == account_filter

                query = (
                    select(*combined_select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                        account_condition,
                    )
                )
            else:
                query = (
                    select(*combined_select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                    )
                )

            # Add joins for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Apply project_id filter early if present
            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

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

    def get_transfer_reason_distribution(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple[object, ...]]:
        """
        Get transfer reason category counts and agent-fault counts.

        Returns:
            list[tuple]: (group_fields..., transfer_reason_category, count, agent_fault_count)
        """
        try:
            start_time = time.time()
            select_fields, group_fields = self._build_group_fields(group_by)

            select_fields.extend(
                [
                    PhoneCall.transfer_reason_category.label(
                        "transfer_reason_category"
                    ),
                    func.count(PhoneCall.id).label("count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (PhoneCall.transfer_agent_was_at_fault.is_(True), 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("agent_fault_count"),
                ]
            )

            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]

                if isinstance(account_filter, list):
                    account_condition = User.account_id.in_(account_filter)
                else:
                    account_condition = User.account_id == account_filter

                query = (
                    select(*select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        PhoneCall.transfer_reason_category.isnot(None),
                        ~Conversation.is_test,
                        account_condition,
                    )
                )
            else:
                query = (
                    select(*select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        PhoneCall.transfer_reason_category.isnot(None),
                        ~Conversation.is_test,
                    )
                )

            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

            group_fields_with_reason = [
                *group_fields,
                PhoneCall.transfer_reason_category,
            ]
            query = query.group_by(*group_fields_with_reason).order_by(
                func.count(PhoneCall.id).desc(),
                PhoneCall.transfer_reason_category.asc(),
            )

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            elapsed = time.time() - start_time
            logger.info(
                "AnalyticsRepository: Transfer reason distribution query executed "
                f"in {elapsed:.3f}s, returned {len(rows)} rows"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting transfer reason distribution: {e}")
            return []

    def get_call_insights(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[CallInsightsRow]:
        """Return call-level rows for business review call insights."""
        try:
            transfer_events = (
                select(
                    ToolCallRecord.conversation_id.label("conversation_id"),
                    func.min(ToolCallRecord.created_at).label("transfer_requested_at"),
                )
                .where(ToolCallRecord.tool_name.ilike("%call_transfer%"))
                .group_by(ToolCallRecord.conversation_id)
                .subquery()
            )

            PriorPhoneCall = aliased(PhoneCall)
            PriorConversation = aliased(Conversation)
            prior_calls = (
                select(func.count(PriorPhoneCall.id))
                .select_from(PriorPhoneCall)
                .join(
                    PriorConversation,
                    PriorPhoneCall.conversation_id == PriorConversation.id,
                )
                .where(
                    PriorConversation.user_id == User.id,
                    PriorPhoneCall.created_at < PhoneCall.created_at,
                )
            )

            contact_destination = (
                select(Contact.phone_number)
                .select_from(Contact)
                .join(ProjectContact, ProjectContact.contact_id == Contact.id)
                .where(
                    ProjectContact.project_id == Conversation.project_id,
                    Contact.role == Conversation.transfer_purpose,
                )
                .order_by(Contact.created_at.asc())
                .limit(1)
                .scalar_subquery()
            )

            query = (
                select(
                    PhoneCall.call_id,
                    PhoneCall.conversation_id,
                    PhoneCall.created_at,
                    PhoneCall.duration,
                    PhoneCall.ended_reason,
                    PhoneCall.transfer_reason_category,
                    Conversation.is_test,
                    Conversation.transfer_purpose,
                    User.id.label("user_id"),
                    User.channel_identifiers,
                    Account.id.label("account_id"),
                    Account.name.label("account_name"),
                    Conversation.project_id,
                    Project.name.label("project_name"),
                    Project.timezone,
                    Project.business_hours,
                    Project.store_hours,
                    func.coalesce(
                        contact_destination,
                        Project.transfer_phone_number,
                    ).label("transfer_destination"),
                    transfer_events.c.transfer_requested_at,
                    prior_calls.scalar_subquery().label("prior_call_count"),
                )
                .select_from(PhoneCall)
                .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .join(Account, User.account_id == Account.id)
                .outerjoin(Project, Conversation.project_id == Project.id)
                .outerjoin(
                    transfer_events,
                    transfer_events.c.conversation_id == Conversation.id,
                )
                .where(PhoneCall.created_at.between(start_date, end_date))
            )

            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]
                if isinstance(account_filter, list):
                    query = query.where(User.account_id.in_(account_filter))
                else:
                    query = query.where(User.account_id == account_filter)

            if filter_by and "project_id" in filter_by:
                project_filter = filter_by["project_id"]
                if isinstance(project_filter, list):
                    query = query.where(Conversation.project_id.in_(project_filter))
                else:
                    query = query.where(Conversation.project_id == project_filter)

            result = self.session.execute(query.order_by(PhoneCall.created_at.desc()))
            return [cast(CallInsightsRow, tuple(row)) for row in result.all()]

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting call insights: {e}")
            return []

    def get_call_quality_distribution(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[tuple[object, ...]]:
        """
        Get post-call quality classifier label counts.

        Returns:
            list[tuple]: (group_fields..., call_quality_label, count)
        """
        try:
            start_time = time.time()
            select_fields, group_fields = self._build_group_fields(group_by)

            select_fields.extend(
                [
                    PhoneCall.call_quality_label.label("call_quality_label"),
                    func.count(PhoneCall.id).label("count"),
                ]
            )

            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]

                if isinstance(account_filter, list):
                    account_condition = User.account_id.in_(account_filter)
                else:
                    account_condition = User.account_id == account_filter

                query = (
                    select(*select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        PhoneCall.call_quality_label.isnot(None),
                        ~Conversation.is_test,
                        account_condition,
                    )
                )
            else:
                query = (
                    select(*select_fields)
                    .select_from(PhoneCall)
                    .join(Conversation, PhoneCall.conversation_id == Conversation.id)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .where(
                        PhoneCall.created_at.between(start_date, end_date),
                        PhoneCall.call_quality_label.isnot(None),
                        ~Conversation.is_test,
                    )
                )

            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

            group_fields_with_label = [
                *group_fields,
                PhoneCall.call_quality_label,
            ]
            query = query.group_by(*group_fields_with_label).order_by(
                func.count(PhoneCall.id).desc(),
                PhoneCall.call_quality_label.asc(),
            )

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            elapsed = time.time() - start_time
            logger.info(
                "AnalyticsRepository: Call quality distribution query executed "
                f"in {elapsed:.3f}s, returned {len(rows)} rows"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting call quality distribution: {e}")
            return []

    def get_conversion_summary(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: list[str] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
        exclude_eval_calls: bool = False,
        exclude_caller_numbers: list[str] | None = None,
    ) -> list[tuple]:
        """
        Get conversion metrics showing how many conversations lead to orders,
        reservations, and waitlist entries.

        Args:
            start_date: Start date for filtering
            end_date: End date for filtering
            group_by: List of fields to group by
            filter_by: Dict of filters
            exclude_eval_calls: If True, exclude conversations with call_id starting with 'eval-'
            exclude_caller_numbers: List of phone numbers to exclude (test numbers)

        Returns:
            list[tuple]: (group_fields...,
                         total_conversations, conversations_with_orders,
                         paid_orders, total_subtotal, paid_total,
                         total_reservations, total_waitlists)
        """
        try:
            start_time = time.time()
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
                    # Orders with paid status (case-insensitive)
                    func.count(
                        case(
                            (func.lower(Order.status) == "paid", Order.id),
                            else_=None,
                        )
                    ).label("paid_orders"),
                    # Total subtotal (monetary value) from all orders
                    func.coalesce(func.sum(Order.subtotal), 0).label("total_subtotal"),
                    # Paid total (monetary value) from only paid orders (case-insensitive)
                    func.coalesce(
                        func.sum(
                            case(
                                (func.lower(Order.status) == "paid", Order.subtotal),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("paid_total"),
                    # Reservations (entry_type='reservation')
                    func.count(
                        case(
                            (Reservation.entry_type == "reservation", Reservation.id),
                            else_=None,
                        )
                    ).label("total_reservations"),
                    # Waitlists (entry_type='waitlist')
                    func.count(
                        case(
                            (Reservation.entry_type == "waitlist", Reservation.id),
                            else_=None,
                        )
                    ).label("total_waitlists"),
                ]
            )

            # Build query with early filtering optimization
            if filter_by and "account_id" in filter_by:
                account_filter = filter_by["account_id"]

                # Handle both single UUID and list of UUIDs
                if isinstance(account_filter, list):
                    account_condition = User.account_id.in_(account_filter)
                    integration_condition = Integration.account_id.in_(account_filter)
                else:
                    account_condition = User.account_id == account_filter
                    integration_condition = Integration.account_id == account_filter

                query = (
                    select(*select_fields)
                    .select_from(Conversation)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .outerjoin(Order, Conversation.id == Order.conversation_id)
                    .outerjoin(
                        Reservation, Conversation.id == Reservation.conversation_id
                    )
                    .where(
                        Conversation.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                        account_condition,
                        # Include accounts with POS or reservation integrations
                        exists(
                            select(1)
                            .select_from(Integration)
                            .where(
                                integration_condition,
                                or_(
                                    Integration.integration_type == IntegrationType.pos,
                                    Integration.integration_type
                                    == IntegrationType.reservation,
                                ),
                            )
                        ),
                    )
                )
            else:
                query = (
                    select(*select_fields)
                    .select_from(Conversation)
                    .join(User, Conversation.user_id == User.id)
                    .join(Account, User.account_id == Account.id)
                    .outerjoin(Order, Conversation.id == Order.conversation_id)
                    .outerjoin(
                        Reservation, Conversation.id == Reservation.conversation_id
                    )
                    .where(
                        Conversation.created_at.between(start_date, end_date),
                        ~Conversation.is_test,
                        # Include accounts with POS or reservation integrations
                        exists(
                            select(1)
                            .select_from(Integration)
                            .where(
                                Integration.account_id == User.account_id,
                                or_(
                                    Integration.integration_type == IntegrationType.pos,
                                    Integration.integration_type
                                    == IntegrationType.reservation,
                                ),
                            )
                        ),
                    )
                )

            # Exclude eval pipeline calls (call_id starts with 'eval-')
            if exclude_eval_calls:
                query = query.where(
                    not_(Conversation.call_id.like("eval-%"))
                    | Conversation.call_id.is_(None)
                )

            # Exclude conversations from test phone numbers
            if exclude_caller_numbers:
                query = query.where(
                    ~User.channel_identifiers.overlap(exclude_caller_numbers)
                )

            # Add Project join if needed for grouping
            if group_by and "project_id" in group_by:
                query = query.join(Project, Conversation.project_id == Project.id)

            # Apply project_id filter early if present
            if filter_by and "project_id" in filter_by:
                project_id = filter_by["project_id"]
                if isinstance(project_id, list):
                    query = query.where(Conversation.project_id.in_(project_id))
                else:
                    query = query.where(Conversation.project_id == project_id)

            # Apply grouping
            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [tuple(row) for row in result.all()]

            elapsed = time.time() - start_time
            logger.info(
                f"AnalyticsRepository: Conversion summary query executed in {elapsed:.3f}s, returned {len(rows)} rows"
            )
            return rows

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting conversion summary: {e}")
            return []

    def get_ordering_revenue_metrics(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        group_by: Literal["date", "store"] | None = None,
        filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
    ) -> list[dict[str, object]]:
        """
        Get revenue metrics for Palona-created orders.
        """
        try:
            start_time = time.time()
            order_date = func.date(Conversation.created_at)
            paid_order = func.lower(Order.status) == "paid"
            has_tracking_link = and_(
                Order.tracking_link.isnot(None),
                func.length(func.trim(Order.tracking_link)) > 0,
            )
            paid_toast_checkout_order = and_(
                Order.vendor == IntegrationProvider.toast,
                exists(
                    select(1)
                    .select_from(ToastCheckoutSession)
                    .where(
                        ToastCheckoutSession.conversation_id == Order.conversation_id,
                        ToastCheckoutSession.order_external_id == Order.order_id,
                        func.lower(ToastCheckoutSession.status) == "paid",
                    )
                ),
            )
            has_payment_link_evidence = or_(
                has_tracking_link,
                paid_toast_checkout_order,
            )
            adora_pay_in_store_order = and_(
                Order.vendor == IntegrationProvider.adora,
                not_(has_tracking_link),
            )
            toast_pay_in_store_order = and_(
                Order.vendor == IntegrationProvider.toast,
                paid_order,
                not_(has_payment_link_evidence),
            )
            payment_link_order = and_(paid_order, has_payment_link_evidence)
            pay_in_store_order = or_(adora_pay_in_store_order, toast_pay_in_store_order)
            palona_revenue_order = or_(payment_link_order, pay_in_store_order)
            fulfillment = func.lower(func.coalesce(Order.fulfillment_strategy, ""))
            takeout_order = fulfillment.in_(
                ("takeout", "take_out", "pickup", "pick_up")
            )
            delivery_order = fulfillment == "delivery"

            select_fields = []
            group_fields = []

            if group_by == "date":
                date_field = order_date.label("date")
                select_fields.append(date_field)
                group_fields.append(date_field)
            elif group_by == "store":
                select_fields.extend(
                    [
                        Order.store_id.label("store_id"),
                        Conversation.project_id.label("project_id"),
                        Project.name.label("project_name"),
                    ]
                )
                group_fields.extend(
                    [Order.store_id, Conversation.project_id, Project.name]
                )

            select_fields.extend(
                [
                    func.count(Order.id).label("total_orders"),
                    func.coalesce(func.sum(Order.subtotal), 0).label(
                        "total_order_value"
                    ),
                    func.coalesce(
                        func.sum(case((palona_revenue_order, Order.subtotal), else_=0)),
                        0,
                    ).label("palona_revenue"),
                    func.count(case((payment_link_order, Order.id), else_=None)).label(
                        "payment_link_orders"
                    ),
                    func.coalesce(
                        func.sum(case((payment_link_order, Order.subtotal), else_=0)),
                        0,
                    ).label("payment_link_revenue"),
                    func.count(case((pay_in_store_order, Order.id), else_=None)).label(
                        "pay_in_store_orders"
                    ),
                    func.coalesce(
                        func.sum(case((pay_in_store_order, Order.subtotal), else_=0)),
                        0,
                    ).label("pay_in_store_revenue"),
                    func.count(case((takeout_order, Order.id), else_=None)).label(
                        "takeout_orders"
                    ),
                    func.coalesce(
                        func.sum(case((takeout_order, Order.subtotal), else_=0)),
                        0,
                    ).label("takeout_revenue"),
                    func.count(case((delivery_order, Order.id), else_=None)).label(
                        "delivery_orders"
                    ),
                    func.coalesce(
                        func.sum(case((delivery_order, Order.subtotal), else_=0)),
                        0,
                    ).label("delivery_revenue"),
                ]
            )

            query = (
                select(*select_fields)
                .select_from(Order)
                .join(Conversation, Order.conversation_id == Conversation.id)
                .join(User, Conversation.user_id == User.id)
                .where(
                    Conversation.created_at.between(start_date, end_date),
                    ~Conversation.is_test,
                    Order.subtotal.isnot(None),
                    exists(
                        select(1)
                        .select_from(Integration)
                        .where(
                            Integration.account_id == User.account_id,
                            Integration.integration_type == IntegrationType.pos,
                        )
                    ),
                )
            )
            if group_by == "store":
                query = query.outerjoin(Project, Conversation.project_id == Project.id)

            query = self._apply_filters(query, filter_by)

            if group_fields:
                query = query.group_by(*group_fields)

            result = self.session.execute(query)
            rows = [dict(row) for row in result.mappings().all()]

            elapsed = time.time() - start_time
            logger.info(
                "AnalyticsRepository: Ordering revenue metrics query executed in "
                f"{elapsed:.3f}s, returned {len(rows)} rows"
            )
            return rows
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error getting ordering revenue metrics: {e}")
            return []
