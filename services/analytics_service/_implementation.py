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

from ._utils import (
    _enforce_hierarchy_order,
    process_analytics_data_generic,
    validate_date_range,
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


def get_account_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Get Active Users, Message Turns analytics data for a given account within a date range.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation. If None, defaults to 7 days ago
        end_date (datetime | None): End date for the calculation. If None, defaults to today

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    try:
        # Validate the date range
        start_date, end_date = validate_date_range(start_date, end_date)

        # Ensure account filtering is applied
        if filter_by is None:
            filter_by = {}

        # Debug: Log what we received
        logger.info(f"Analytics Service: Received filter_by: {filter_by}")

        # Always filter by the account ID
        filter_by["account_id"] = account_id

        # Debug: Log what we're passing to repository
        logger.info(f"Analytics Service: Passing filter_by to repository: {filter_by}")

        # Fetch and process active users data using service function
        users_report = get_active_users(
            session=session,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            filter_by=filter_by,
        )

        # Fetch and process Message Turns data using service function
        turns_report = get_turns_summary(
            session=session,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            filter_by=filter_by,
        )
        calls_report = get_calls_time_summary(
            session=session,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            filter_by=filter_by,
        )
        call_info_report = get_calls_info_summary(
            session=session,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            filter_by=filter_by,
        )

        conversion_report = get_conversion_summary(
            session=session,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by,
            filter_by=filter_by,
        )

        # Create and return reports
        reports = [
            PerformanceReport(
                name=AnalyticsReportType.ACTIVE_USERS.name, data=users_report
            ),
            PerformanceReport(
                name=AnalyticsReportType.MESSAGE_TURNS.name, data=turns_report
            ),
            PerformanceReport(
                name=AnalyticsReportType.CALL_METRICS.name, data=calls_report
            ),
            PerformanceReport(
                name=AnalyticsReportType.CALL_INFO_DISTRIBUTION.name,
                data=call_info_report,
            ),
            PerformanceReport(
                name=AnalyticsReportType.CONVERSION_METRICS.name,
                data=conversion_report,
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


def get_active_users(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get active users analytics with flexible grouping and filtering.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['account_id', 'project_id'] (date is automatically prepended)
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'active_users': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get Active Users (grouped data for details)
        active_users_data = analytics_repo.get_active_users(
            start_date=start_date,
            end_date=end_date,
            group_by=ordered_group_by,
            filter_by=filter_by,
        )

        # Get Active Users Totals (NO grouping to avoid duplication)
        active_users_totals_data = analytics_repo.get_active_users(
            start_date=start_date,
            end_date=end_date,
            group_by=[],  # No grouping for accurate totals
            filter_by=filter_by,
        )

        # Process Active Users Data using generic architecture
        active_users_report = process_analytics_data_generic(
            active_users_data,
            ordered_group_by,
            AnalyticsReportType.ACTIVE_USERS.metrics_config,
        )

        # Calculate totals from ungrouped data (accurate totals)
        totals = process_analytics_data_generic(
            active_users_totals_data,
            None,
            AnalyticsReportType.ACTIVE_USERS.metrics_config,
            calculate_totals=True,
        )

        return {
            "active_users": active_users_report,
            "totals": totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating active users report: {e}")
        raise


def get_turns_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get conversation turns summary with flexible grouping and filtering.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['account_id', 'project_id'] (date is automatically prepended)
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'turn_distribution': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get Turn Distribution (grouped data for details)
        turn_distribution_data = analytics_repo.get_turns_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=ordered_group_by,
            filter_by=filter_by,
        )

        # Get Turn Totals (NO grouping to avoid duplication)
        turn_totals_data = analytics_repo.get_turns_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=[],  # No grouping for accurate totals
            filter_by=filter_by,
        )

        # Process Turn Distribution Data using generic architecture
        turn_distribution = process_analytics_data_generic(
            turn_distribution_data,
            ordered_group_by,
            AnalyticsReportType.MESSAGE_TURNS.metrics_config,
        )

        # Calculate turns totals from ungrouped data (accurate totals)
        turns_totals = process_analytics_data_generic(
            turn_totals_data,
            None,
            AnalyticsReportType.MESSAGE_TURNS.metrics_config,
            calculate_totals=True,
        )

        return {
            "turn_distribution": turn_distribution,
            "totals": turns_totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating turns summary: {e}")
        raise


def get_calls_time_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get call time metrics following the same pattern as get_turns_summary.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['date', 'account_id', 'project_id']
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'call_time_metrics': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get Call Time Data (grouped data for details)
        call_time_data = analytics_repo.get_calls_time_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=ordered_group_by,
            filter_by=filter_by,
        )

        # Get Call Time Totals (NO grouping to avoid duplication)
        call_time_totals_data = analytics_repo.get_calls_time_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=[],  # No grouping for accurate totals
            filter_by=filter_by,
        )

        # Process Call Time Data using generic architecture
        call_time_report = process_analytics_data_generic(
            call_time_data,
            ordered_group_by,
            AnalyticsReportType.CALL_METRICS.metrics_config,
        )

        # Calculate totals from ungrouped data (accurate totals)
        totals = process_analytics_data_generic(
            call_time_totals_data,
            None,
            AnalyticsReportType.CALL_METRICS.metrics_config,
            calculate_totals=True,
        )

        return {
            "call_time_metrics": call_time_report,
            "totals": totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating call time summary: {e}")
        raise


def get_calls_info_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """Get call purpose and language distribution - simple like get_calls_time_summary."""
    try:
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order but exclude date
        filtered_group_by = [field for field in group_by if field != "date"]
        ordered_group_by = _enforce_hierarchy_order(filtered_group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get Call Info Data (grouped data for details)
        call_info_data = analytics_repo.get_calls_info_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=ordered_group_by,
            filter_by=filter_by,
        )

        # Get Call Info Totals (NO grouping to avoid duplication)
        call_info_totals_data = analytics_repo.get_calls_info_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=[],  # No grouping for accurate totals
            filter_by=filter_by,
        )

        # Process Call Purpose Distribution (purposes only)
        call_purpose_report = process_analytics_data_generic(
            call_info_data,
            ordered_group_by,
            AnalyticsReportType.CALL_PURPOSE_DISTRIBUTION.metrics_config,
        )

        # Process Call Language Distribution (languages only)
        call_language_report = process_analytics_data_generic(
            call_info_data,
            ordered_group_by,
            AnalyticsReportType.CALL_LANGUAGE_DISTRIBUTION.metrics_config,
        )

        # Calculate separate totals
        call_purpose_totals = process_analytics_data_generic(
            call_info_totals_data,
            None,
            AnalyticsReportType.CALL_PURPOSE_DISTRIBUTION.metrics_config,
            calculate_totals=True,
        )

        call_language_totals = process_analytics_data_generic(
            call_info_totals_data,
            None,
            AnalyticsReportType.CALL_LANGUAGE_DISTRIBUTION.metrics_config,
            calculate_totals=True,
        )

        return {
            "call_purpose_distribution": call_purpose_report,
            "call_language_distribution": call_language_report,
            "totals": {
                "purposes": call_purpose_totals,
                "languages": call_language_totals,
            },
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating call info summary: {e}")
        raise


def get_conversion_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get conversion metrics showing how many conversations lead to orders and paid orders.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['account_id', 'project_id'] (date is automatically prepended)
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'conversion_metrics': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get Conversion Data (grouped data for details)
        conversion_data = analytics_repo.get_conversion_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=ordered_group_by,
            filter_by=filter_by,
        )

        # Get Conversion Totals (NO grouping to avoid duplication)
        conversion_totals_data = analytics_repo.get_conversion_summary(
            start_date=start_date,
            end_date=end_date,
            group_by=[],  # No grouping for accurate totals
            filter_by=filter_by,
        )

        # Process Conversion Data using generic architecture
        conversion_report = process_analytics_data_generic(
            conversion_data,
            ordered_group_by,
            AnalyticsReportType.CONVERSION_METRICS.metrics_config,
        )

        # Calculate totals from ungrouped data (accurate totals)
        totals = process_analytics_data_generic(
            conversion_totals_data,
            None,
            AnalyticsReportType.CONVERSION_METRICS.metrics_config,
            calculate_totals=True,
        )

        return {
            "conversion_metrics": conversion_report,
            "totals": totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating conversion summary: {e}")
        raise


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
