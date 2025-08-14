import asyncio
import os
import uuid
from datetime import datetime

from mixpanel import Mixpanel
from sqlalchemy.orm import Session

import db
from api.schemas.admin.analytics import AnalyticsReportType
from api.schemas.admin.analytics import Event as AnalyticsEvent
from api.schemas.admin.analytics import GetAllReportsResponse, PerformanceReport
from utils.log import logger

from ._utils import handle_analytics_date_range, process_analytics_results_to_dict

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
        start_date, end_date, formatted_range = handle_analytics_date_range(
            start_date, end_date
        )

        logger.info(
            f"Analytics: Fetching analytics for account {account_id} from {formatted_range}"
        )
        message_repo = db.MessageRepository(session)
        transaction_repo = db.TransactionRepository(session)

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
        order_result = transaction_repo.get_order_value(
            account_id, start_date, end_date
        )

        # Process Order Total data (uses DB column key via report_name)
        order_value_data = process_analytics_results_to_dict(
            order_result,
            start_date,
            end_date,
            AnalyticsReportType.ORDER_TOTAL,
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
