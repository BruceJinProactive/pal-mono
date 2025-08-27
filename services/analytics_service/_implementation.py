import asyncio
import os
import uuid
from datetime import datetime

from mixpanel import Mixpanel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.admin.analytics import AnalyticsReportType
from api.schemas.admin.analytics import Event as AnalyticsEvent
from api.schemas.admin.analytics import GetAllReportsResponse, PerformanceReport
from utils.log import logger

from ._utils import (
    handle_analytics_date_range,
    normalize_datetime_to_utc,
    process_analytics_results_to_dict,
)

# BRUCETODO: DELETE - Mixpanel related variables
MIXPANEL_BASE_URL = "https://mixpanel.com/api"
MIXPANEL_PROJECT_ID = 3584752
MIXPANEL_WORKSPACE_ID = 9701744
BOOKMARK_ID_MAPPING = {
    "ORDER": 81979859,
}
MIXPANEL_REPORTS = [
    (81979859, "Total Order Value"),
]


def get_analytics_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> GetAllReportsResponse:
    """
    Get DAU, Message Turns, Order Total, and Order Numbers analytics data for a given account within a date range.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation. If None, defaults to 7 days ago
        end_date (datetime | None): End date for the calculation. If None, defaults to today

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    try:
        # Handle date range validation and defaults
        start_date, end_date = handle_analytics_date_range(start_date, end_date)
        message_repo = db.MessageRepository(session)
        order_repo = db.OrderRepository(session)

        # Fetch and process DAU data
        dau_result = message_repo.get_daily_active_users(
            account_id, start_date, end_date
        )
        dau_data = process_analytics_results_to_dict(
            dau_result, start_date, end_date, AnalyticsReportType.DAU
        )

        # Fetch and process Message Turns data
        message_turns_result = message_repo.get_daily_message_turns(
            account_id, start_date, end_date
        )
        message_turns_data = process_analytics_results_to_dict(
            message_turns_result,
            start_date,
            end_date,
            AnalyticsReportType.MESSAGE_TURNS,
        )
        # Fetch order data (contains both value and count)
        order_result = order_repo.get_order_value(account_id, start_date, end_date)

        # Process Order Total data (uses DB column key via report_name)
        order_value_data = process_analytics_results_to_dict(
            order_result,
            start_date,
            end_date,
            AnalyticsReportType.ORDER_TOTAL,
        )
        logger.info(
            f"Analytics: Processed Message Turns data for account {AnalyticsReportType.ORDER_TOTAL} from {order_value_data}"
        )

        # Create and return reports
        reports = [
            PerformanceReport(name=AnalyticsReportType.DAU, data=dau_data),
            PerformanceReport(
                name=AnalyticsReportType.MESSAGE_TURNS, data=message_turns_data
            ),
            PerformanceReport(
                name=AnalyticsReportType.ORDER_TOTAL, data=order_value_data
            ),
        ]

        return GetAllReportsResponse(reports=reports)

    except ValueError as e:
        logger.error(f"Analytics: Date validation error for account {account_id}: {e}")
        return GetAllReportsResponse(reports=[])
    except Exception as e:
        logger.error(
            f"Analytics: Error calculating analytics for account {account_id}: {e}"
        )
        logger.exception("Analytics: Full analytics exception traceback:")
        return GetAllReportsResponse(reports=[])


# BRUCETODO: DELETE - Mixpanel related variables
def track_event(user_id: str, event_name: AnalyticsEvent, event_properties: dict):
    def _track():
        try:
            MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
            mp = None
            if MIXPANEL_PROJECT_TOKEN:
                mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)
            if mp:
                runtime_env = os.getenv("RUNTIME_ENV", "dev")
                event_properties["runtime_env"] = runtime_env
                mp.track(user_id, event_name, event_properties)
        except Exception as e:
            logger.error(
                f"Analytics: Error tracking event {event_name} for user {user_id}: {e}"
            )

    asyncio.create_task(asyncio.to_thread(_track))


def get_all_accounts_conversion_stats(
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """
    Get conversion statistics for all accounts with elegant data combination.
    Always includes a TOTAL row with aggregated data.

    Args:
        session: Database session (must be Session)
        start_date: Optional start date for filtering (converted to UTC)
        end_date: Optional end date for filtering (converted to UTC)

    Returns:
        list[dict]: List of conversion statistics for all accounts (includes TOTAL row)
    """
    try:
        if isinstance(session, AsyncSession):
            raise ValueError(
                "get_all_accounts_conversion_stats requires a synchronous Session"
            )

        # Normalize datetime inputs to UTC
        start_date = normalize_datetime_to_utc(start_date)
        end_date = normalize_datetime_to_utc(end_date)

        # Get data from both repositories
        conv_repo = db.ConversationRepository(session)
        order_repo = db.OrderRepository(session)

        conversation_data = conv_repo.get_conversation_counts_by_account(
            start_date=start_date, end_date=end_date
        )

        order_data = order_repo.get_order_conversation_counts_by_account(
            start_date=start_date, end_date=end_date
        )

        # Combine data elegantly
        return _combine_conversion_data(conversation_data, order_data)

    except Exception as e:
        logger.error(f"Analytics: Error getting all accounts conversion stats: {e}")
        return []


def get_account_conversion_stats(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict | None:
    """
    Get conversion statistics for a single account.

    Args:
        session: Database session (must be Session)
        account_id: The specific account ID to get stats for
        start_date: Optional start date for filtering (converted to UTC)
        end_date: Optional end date for filtering (converted to UTC)

    Returns:
        dict | None: Conversion statistics for the account, or None if not found
    """
    try:
        if isinstance(session, AsyncSession):
            raise ValueError(
                "get_account_conversion_stats requires a synchronous Session"
            )

        # Normalize datetime inputs to UTC
        start_date = normalize_datetime_to_utc(start_date)
        end_date = normalize_datetime_to_utc(end_date)

        # Get data from both repositories for specific account
        conv_repo = db.ConversationRepository(session)
        order_repo = db.OrderRepository(session)

        conversation_data = conv_repo.get_conversation_counts_by_account(
            account_id=account_id, start_date=start_date, end_date=end_date
        )

        order_data = order_repo.get_order_conversation_counts_by_account(
            account_id=account_id, start_date=start_date, end_date=end_date
        )

        # Combine data for single account
        combined_data = _combine_conversion_data(conversation_data, order_data)

        return combined_data[0] if combined_data else None

    except Exception as e:
        logger.error(f"Analytics: Error getting account conversion stats: {e}")
        return None


def _combine_conversion_data(
    conversation_data: list[tuple], order_data: list[tuple]
) -> list[dict]:
    """
    Elegantly combine conversation and order data into formatted results.

    Args:
        conversation_data: List of tuples (account_id, account_name, total_conversations)
        order_data: List of tuples (account_id, account_name, conversations_with_orders, conversations_with_paid_orders)

    Returns:
        list[dict]: Combined and formatted conversion statistics
    """
    # Create lookup map for order data
    order_map = {
        row[0]: {  # account_id as key
            "conversations_with_orders": row[2],
            "conversations_with_paid_orders": row[3],
        }
        for row in order_data
    }

    combined_results = []

    for conv_row in conversation_data:
        account_id, account_name, total_conversations = conv_row

        # Get corresponding order data (default to 0 if no orders)
        order_info = order_map.get(
            account_id,
            {"conversations_with_orders": 0, "conversations_with_paid_orders": 0},
        )

        # Calculate conversion rates
        checkout_conversion_rate = (
            (order_info["conversations_with_orders"] / total_conversations * 100)
            if total_conversations > 0
            else 0.0
        )

        paid_rate = (
            (
                order_info["conversations_with_paid_orders"]
                / order_info["conversations_with_orders"]
                * 100
            )
            if order_info["conversations_with_orders"] > 0
            else 0.0
        )

        combined_results.append(
            {
                "account_id": str(account_id) if account_id else None,
                "account_name": account_name,
                "total_conversations": total_conversations,
                "conversations_with_orders": order_info["conversations_with_orders"],
                "conversations_with_paid_orders": order_info[
                    "conversations_with_paid_orders"
                ],
                "checkout_conversion_rate": round(checkout_conversion_rate, 2),
                "paid_rate": round(paid_rate, 2),
            }
        )

    return combined_results
