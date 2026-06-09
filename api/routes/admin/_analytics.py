import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from api.schemas.admin.analytics import (
    AnalyticsReportType,
    GetAllReportsResponse,
    PerformanceReport,
)
from api.schemas.admin.ordering_metrics import OrderingMetricsResponse
from services.account_service import get_account
from services.analytics_service import (
    get_account_reports,
    get_ordering_metrics,
    get_reports,
)
from utils.log import logger

from . import UserContext
from ._utils import not_found_error


async def get_accounts_reports(
    account_name: str | None,
    context: UserContext,
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    filter_by: dict | None = None,
    group_by: list[str] | None = None,
) -> GetAllReportsResponse:
    """
    Get analytics data with project breakdowns.

    Args:
        account_name (str): The name of the account to get analytics for.
        context (UserContext): User context for authorization.
        session (Session): The SQLAlchemy session for database access.
        start_date (datetime): Start date for the analytics.
        end_date (datetime): End date for the analytics.

    Returns:
        GetAllReportsResponse: Unified response with all analytics reports including project breakdowns.
    """
    try:
        if not account_name:
            logger.warning(
                "Analytics: No account name provided, returning empty reports"
            )
            return GetAllReportsResponse(reports=[])

        account = get_account(session, account_name)
        if not account:
            raise not_found_error(f"Account {account_name} not found.")

        # Get analytics data
        analytics_reports = await get_account_reports(
            session,
            account.id,
            start_date,
            end_date,
            group_by,
            filter_by,
        )

        if not analytics_reports.reports:
            logger.warning(
                f"Analytics: No analytics reports found for account {account_name}."
            )
            # Return empty response if no reports found
            return GetAllReportsResponse(reports=[])
        return analytics_reports

    except Exception as e:
        logger.error(f"Analytics: Error in get_reports: {e}")
        logger.exception("Analytics: Full traceback:")
        # Return empty response on error
        empty_reports: list[PerformanceReport] = [
            PerformanceReport(name=AnalyticsReportType.ACTIVE_USERS.name, data={}),
            PerformanceReport(
                name=AnalyticsReportType.MESSAGE_TURNS.name,
                data={},
            ),
            PerformanceReport(name=AnalyticsReportType.CALL_METRICS.name, data={}),
            PerformanceReport(
                name=AnalyticsReportType.CALL_INFO_DISTRIBUTION.name, data={}
            ),
        ]
        result: GetAllReportsResponse = GetAllReportsResponse(reports=empty_reports)
        return result


async def get_account_ordering_metrics(
    account_name: str,
    context: UserContext,
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> OrderingMetricsResponse:
    """
    Get ordering metrics and ordering capability status for an account.
    """
    del context
    account = get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found.")

    return await get_ordering_metrics(
        session=session,
        account_id=account.id,
        account_name=account_name,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
    )


async def get_company_reports(
    context: UserContext,
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
) -> GetAllReportsResponse:
    """
    Get analytics data with company breakdowns.
    """

    return await get_reports(
        session=session,
        account_id=None,
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
    )
