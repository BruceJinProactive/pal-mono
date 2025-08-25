from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.schemas.admin.analytics import (
    AnalyticsReportType,
    AnalyticsResponse,
    GetAllReportsResponse,
    PerformanceReport,
)
from services import analytics_service
from services.account_service import get_account
from utils.log import logger

from . import UserContext
from ._auth import authorize_user_account
from ._utils import not_found_error


async def get_reports(
    account_name: str,
    context: UserContext,
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
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
        authorize_user_account(context, account_name)
        account = get_account(session, account_name)
        if not account:
            raise not_found_error(f"Account {account_name} not found.")

        # Get analytics data
        analytics_reports = analytics_service.get_analytics_reports(
            session=session,
            account_id=account.id,
            start_date=start_date,
            end_date=end_date,
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
            PerformanceReport(
                name=AnalyticsReportType.DAU, data=AnalyticsResponse(analytics_data={})
            ),
            PerformanceReport(
                name=AnalyticsReportType.MESSAGE_TURNS,
                data=AnalyticsResponse(analytics_data={}),
            ),
        ]
        result: GetAllReportsResponse = GetAllReportsResponse(reports=empty_reports)
        return result


async def generate_daily_report(
    account_name: str,
    context: UserContext,
    session: Session,
    channel: str | None = None,
) -> dict:
    """
    Generate and send daily report to Slack via bot.

    Args:
        account_name (str): The name of the account (for authorization).
        context (UserContext): User context for authorization.
        session (Session): The SQLAlchemy session for database access.
        channel (str): Optional Slack channel to send to.

    Returns:
        dict: Status of the operation.
    """
    try:
        logger.info(f"[Slackbot]: Generating daily report for account {account_name}")
        authorize_user_account(context, account_name)
        account = get_account(session, account_name)
        if not account:
            raise not_found_error(f"Account {account_name} not found.")

        # Send the report via bot
        result = await analytics_service.send_daily_report_to_slack(channel)

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analytics: Error in generate_daily_report: {e}")
        logger.exception("Analytics: Full traceback:")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate daily report: {str(e)}"
        )
