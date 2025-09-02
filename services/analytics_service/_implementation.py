import asyncio
import os
import time
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


async def get_account_reports(
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
        start_time = time.time()
        logger.info(
            f"🚀 Analytics_time: Starting reports for account {account_id} at {time.strftime('%H:%M:%S.%f')[:-3]}"
        )

        # Validate the date range
        validation_start = time.time()
        start_date, end_date = validate_date_range(start_date, end_date)
        validation_time = time.time() - validation_start
        logger.info(f"⏱️  Analytics_time: Date validation took {validation_time:.6f}s")

        # Ensure account filtering is applied
        filter_start = time.time()
        if filter_by is None:
            filter_by = {}

        # Debug: Log what we received
        logger.info(f"Analytics Service: Received filter_by: {filter_by}")

        # Always filter by the account ID
        filter_by["account_id"] = account_id

        # Debug: Log what we're passing to repository
        logger.info(f"Analytics Service: Passing filter_by to repository: {filter_by}")
        filter_time = time.time() - filter_start
        logger.info(f"⏱️  Analytics_time: Filter setup took {filter_time:.6f}s")

        # Execute all analytics queries in parallel for better performance
        parallel_start = time.time()
        logger.info(
            f"🔄 Analytics_time: Starting 5 parallel queries at {time.strftime('%H:%M:%S.%f')[:-3]}..."
        )
        (
            users_report,
            turns_report,
            calls_report,
            call_info_report,
            conversion_report,
        ) = await asyncio.gather(
            asyncio.to_thread(
                get_active_users,
                session=session,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                get_turns_summary,
                session=session,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                get_calls_time_summary,
                session=session,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                get_calls_info_summary,
                session=session,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                get_conversion_summary,
                session=session,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
        )

        parallel_time = time.time() - parallel_start
        logger.info(
            f"🏁 Analytics_time: Parallel queries completed in {parallel_time:.6f}s at {time.strftime('%H:%M:%S.%f')[:-3]}"
        )

        # Create and return reports
        report_start = time.time()
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

        report_time = time.time() - report_start
        total_time = time.time() - start_time

        logger.info(f"📊 Analytics_time: Report creation took {report_time:.6f}s")
        logger.info(f"✅ Analytics_time: TOTAL TIME: {total_time:.6f}s")
        logger.info(
            f"📈 Analytics_time: BREAKDOWN - Validation: {validation_time:.6f}s | Filter: {filter_time:.6f}s | Queries: {parallel_time:.6f}s | Reports: {report_time:.6f}s"
        )

        return GetAllReportsResponse(reports=reports)

    except ValueError as e:
        logger.error(
            f"Analytics_time: Date validation error for account {account_id}: {e}"
        )
        return GetAllReportsResponse(reports=[])
    except Exception as e:
        logger.error(
            f"Analytics_time: Error calculating analytics for account {account_id}: {e}"
        )
        logger.exception("Analytics_time: Full analytics exception traceback:")
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
        func_start = time.time()
        logger.info(
            f"🔍 Analytics_time: get_active_users starting at {time.strftime('%H:%M:%S.%f')[:-3]}..."
        )

        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get both grouped and total data in parallel to reduce database calls
        db_start = time.time()
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            logger.info(
                "🗄️  Analytics_time: get_active_users running 2 DB queries (grouped + totals)..."
            )
            active_users_data, active_users_totals_data = (
                analytics_repo.get_active_users(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_active_users(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            logger.info(
                "🗄️  Analytics_time: get_active_users running 1 DB query (totals only)..."
            )
            active_users_data = []
            active_users_totals_data = analytics_repo.get_active_users(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        db_time = time.time() - db_start
        logger.info(
            f"🗄️  Analytics_time: get_active_users DB queries took {db_time:.6f}s"
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

        func_time = time.time() - func_start
        logger.info(
            f"✅ Analytics_time: get_active_users completed in {func_time:.6f}s (DB: {db_time:.6f}s) at {time.strftime('%H:%M:%S.%f')[:-3]}"
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
        func_start = time.time()
        logger.info(
            f"🔍 Analytics_time: get_turns_summary starting at {time.strftime('%H:%M:%S.%f')[:-3]}..."
        )

        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        db_start = time.time()
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            logger.info(
                "🗄️  Analytics_time: get_turns_summary running 2 COMPLEX DB queries (grouped + totals)..."
            )
            turn_distribution_data, turn_totals_data = (
                analytics_repo.get_turns_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_turns_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            logger.info(
                "🗄️  Analytics_time: get_turns_summary running 1 COMPLEX DB query (totals only)..."
            )
            turn_distribution_data = []
            turn_totals_data = analytics_repo.get_turns_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        db_time = time.time() - db_start
        logger.info(
            f"🗄️  Analytics_time: get_turns_summary DB queries took {db_time:.6f}s"
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

        func_time = time.time() - func_start
        logger.info(
            f"✅ Analytics_time: get_turns_summary completed in {func_time:.6f}s (DB: {db_time:.6f}s) at {time.strftime('%H:%M:%S.%f')[:-3]}"
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
        func_start = time.time()
        logger.info(
            f"🔍 Analytics_time: get_calls_time_summary starting at {time.strftime('%H:%M:%S.%f')[:-3]}..."
        )

        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        db_start = time.time()
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            logger.info(
                "🗄️  Analytics_time: get_calls_time_summary running 2 DB queries (grouped + totals)..."
            )
            call_time_data, call_time_totals_data = (
                analytics_repo.get_calls_time_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_calls_time_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            logger.info(
                "🗄️  Analytics_time: get_calls_time_summary running 1 DB query (totals only)..."
            )
            call_time_data = []
            call_time_totals_data = analytics_repo.get_calls_time_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        db_time = time.time() - db_start
        logger.info(
            f"🗄️  Analytics_time: get_calls_time_summary DB queries took {db_time:.6f}s"
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

        func_time = time.time() - func_start
        logger.info(
            f"✅ Analytics_time: get_calls_time_summary completed in {func_time:.6f}s (DB: {db_time:.6f}s) at {time.strftime('%H:%M:%S.%f')[:-3]}"
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
        func_start = time.time()
        logger.info(
            f"🔍 Analytics_time: get_calls_info_summary starting at {time.strftime('%H:%M:%S.%f')[:-3]}..."
        )

        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order but exclude date
        filtered_group_by = [field for field in group_by if field != "date"]
        ordered_group_by = _enforce_hierarchy_order(filtered_group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        db_start = time.time()
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            logger.info(
                "🗄️  Analytics_time: get_calls_info_summary running 2 DB queries (grouped + totals)..."
            )
            call_info_data, call_info_totals_data = (
                analytics_repo.get_calls_info_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_calls_info_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            logger.info(
                "🗄️  Analytics_time: get_calls_info_summary running 1 DB query (totals only)..."
            )
            call_info_data = []
            call_info_totals_data = analytics_repo.get_calls_info_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        db_time = time.time() - db_start
        logger.info(
            f"🗄️  Analytics_time: get_calls_info_summary DB queries took {db_time:.6f}s"
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

        func_time = time.time() - func_start
        logger.info(
            f"✅ Analytics_time: get_calls_info_summary completed in {func_time:.6f}s (DB: {db_time:.6f}s) at {time.strftime('%H:%M:%S.%f')[:-3]}"
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
        func_start = time.time()
        logger.info(
            f"🔍 Analytics_time: get_conversion_summary starting at {time.strftime('%H:%M:%S.%f')[:-3]}..."
        )

        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        db_start = time.time()
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            logger.info(
                "🗄️  Analytics_time: get_conversion_summary running 2 DB queries (grouped + totals)..."
            )
            conversion_data, conversion_totals_data = (
                analytics_repo.get_conversion_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_conversion_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            logger.info(
                "🗄️  Analytics_time: get_conversion_summary running 1 DB query (totals only)..."
            )
            conversion_data = []
            conversion_totals_data = analytics_repo.get_conversion_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        db_time = time.time() - db_start
        logger.info(
            f"🗄️  Analytics_time: get_conversion_summary DB queries took {db_time:.6f}s"
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

        func_time = time.time() - func_start
        logger.info(
            f"✅ Analytics_time: get_conversion_summary completed in {func_time:.6f}s (DB: {db_time:.6f}s) at {time.strftime('%H:%M:%S.%f')[:-3]}"
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
                f"Analytics_time: Error tracking event {event_name} for user {user_id}: {e}"
            )

    asyncio.create_task(asyncio.to_thread(_track))
