from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

from api.schemas.admin.analytics import (
    VALID_CHANNELS,
    GetAllReportsResponse,
    PerformanceReport,
)
from services import analytics_service
from services.account_service import get_account
from services.analytics_service import get_report_from_mixpanel
from utils.log import logger

from . import UserContext, _auth
from ._auth import authorize_user_account
from ._utils import not_found_error


def format_analytics_data_as_reports(
    raw_data: dict[str, dict[str, int]], metric_name: str
) -> list[PerformanceReport]:
    """
    Convert raw analytics data to list of Report objects with Mixpanel-style format.

    Args:
        raw_data: Dictionary with date strings as keys and channel counts as values
        metric_name: Name of the metric (e.g., "DAU", "Message Turns")

    Returns:
        List of Report objects matching Mixpanel structure (channels first, then dates)
    """
    # Create the main report with all channels
    report_data = {}

    if raw_data:
        # First, calculate overall totals for each date
        overall_data = {}
        for date_str, channels in raw_data.items():
            overall_data[date_str] = sum(channels.values())

        # Add overall data as the first entry
        report_data["$overall"] = overall_data

        # Organize data by channel first, then by date (matching Mixpanel format)
        for channel in VALID_CHANNELS:
            channel_data = {}
            for date_str, channels in raw_data.items():
                channel_data[date_str] = channels.get(channel, 0)

            # Only include channels that have non-zero data
            if any(value > 0 for value in channel_data.values()):
                report_data[channel] = channel_data
    else:
        # Return empty structure if no data
        report_data = {"$overall": {}}

    # Create a single comprehensive report
    reports = [PerformanceReport(name=metric_name, data=report_data)]

    return reports


def get_report(
    request: Request,
    report_name: str,
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> dict | None:
    """
    Fetches insights data from Mixpanel for a given report name and account.

    Args:
        request (Request): The FastAPI request object containing the headers with the authorization token.
        report_name (str): The name of the report to fetch data for.
        session (Session): The SQLAlchemy session for database access.

    Returns:
        dict | None: The report data from Mixpanel.
    """
    account = _auth.get_account_from_id_token(request, session)
    account_name = account.name
    return get_report_from_mixpanel(report_name, account_name, start_date, end_date)


def get_all_reports(
    account_name: str,
    start_date: datetime,
    end_date: datetime,
) -> list[PerformanceReport]:
    """
    Fetches all insights data from Mixpanel for all reports defined in BOOKMARK_ID_MAPPING.

    Args:
        account_name (str): The name of the account to fetch data for.

    Returns:
        list[PerformanceReport]: A list of PerformanceReport
    """
    reports = analytics_service.get_all_reports_from_mixpanel(
        account_name, start_date, end_date
    )
    return [PerformanceReport(name=name, data=data) for name, data in reports]


async def get_reports(
    account_name: str,
    context: UserContext,
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> GetAllReportsResponse:
    """
    Get unified analytics reports combining database DAU/Message Turns with Mixpanel order reports.

    This endpoint provides:
    - DAU data from database (structured by channel)
    - Message Turns data from database (structured by channel)
    - Order-related reports from Mixpanel (Total Order Value, Checkout Conversion)

    Args:
        account_name (str): The name of the account to get reports for.
        session (Session): The SQLAlchemy session for database access.
        start_date (datetime): Start date for the reports.
        end_date (datetime): End date for the reports.

    Returns:
        GetAllReportsResponse: Unified response with all analytics reports.
    """
    try:
        authorize_user_account(context, account_name)
        account = get_account(session, account_name)
        if not account:
            raise not_found_error(f"Account {account_name} not found.")

        # Get DAU and Message Turns data from database sequentially
        # (Sequential to avoid concurrent session issues)
        raw_dau_data = analytics_service.get_dau(
            session=session,
            account_id=account.id,
            start_date=start_date,
            end_date=end_date,
        )

        raw_message_turns_data = analytics_service.get_daily_message_turns(
            session=session,
            account_id=account.id,
            start_date=start_date,
            end_date=end_date,
        )

    except Exception as e:
        logger.error(f"ERROR in get_reports before formatting: {e}")
        logger.exception("Full traceback:")
        # Return minimal response on error
        return GetAllReportsResponse(
            reports=[
                PerformanceReport(name="DAU", data={"$overall": {}}),
                PerformanceReport(name="Message Turns", data={"$overall": {}}),
            ]
        )

    # Format DAU data as list of reports (aligned with Mixpanel format)
    try:
        formatted_dau_data = format_analytics_data_as_reports(raw_dau_data, "DAU")
    except Exception as e:
        logger.error(f"Error formatting DAU data: {e}")
        formatted_dau_data = [PerformanceReport(name="DAU", data={"$overall": {}})]

    # Format Message Turns data as list of reports (aligned with Mixpanel format)
    try:
        formatted_message_turns_data = format_analytics_data_as_reports(
            raw_message_turns_data, "Message Turns"
        )
    except Exception as e:
        logger.error(f"Error formatting Message Turns data: {e}")
        formatted_message_turns_data = [
            PerformanceReport(name="Message Turns", data={"$overall": {}})
        ]

    # Ensure we always have DAU and Message Turns reports, even if empty
    if not formatted_dau_data:
        formatted_dau_data = [PerformanceReport(name="DAU", data={"$overall": {}})]
    if not formatted_message_turns_data:
        formatted_message_turns_data = [
            PerformanceReport(name="Message Turns", data={"$overall": {}})
        ]

    # Get selected Mixpanel reports (only order-related ones)
    # Filter to only get "Total Order Value" report
    order_related_reports = ["Total Order Value"]
    try:
        all_mixpanel_reports = get_all_reports(account_name, start_date, end_date)
        filtered_mixpanel_reports = [
            report
            for report in all_mixpanel_reports
            if report.name in order_related_reports
        ]
    except Exception as e:
        logger.error(f"Error getting Mixpanel reports: {e}")
        filtered_mixpanel_reports = []

    # Combine all reports into a single flat list
    all_reports = []
    all_reports.extend(formatted_dau_data)
    all_reports.extend(formatted_message_turns_data)
    all_reports.extend(filtered_mixpanel_reports)

    return GetAllReportsResponse(reports=all_reports)
