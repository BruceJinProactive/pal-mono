import uuid
from datetime import datetime

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from api.schemas.admin.analytics import GetAllReportsResponse

from . import _implementation, _slack


async def get_reports(
    session: Session,
    account_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Get all analytics reports for a given account within a date range.
    This is the main analytics function.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation
        end_date (datetime | None): End date for the calculation
        group_by (list[str] | None): List of fields to group by
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    return await _implementation.get_reports(
        session,
        account_id,
        start_date,
        end_date,
        group_by=group_by,
        filter_by=filter_by,
    )


async def get_account_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Wrapper function for backward compatibility. Calls get_reports internally.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime): Start date for the calculation
        end_date (datetime): End date for the calculation
        group_by (list[str] | None): List of fields to group by
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    return await get_reports(
        session,
        account_id,
        start_date,
        end_date,
        group_by=group_by,
        filter_by=filter_by,
    )


async def send_report_to_slack(
    slack_channel: str | None = None,
    client: AsyncWebClient | None = None,
    session: Session | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    account_name: str | None = None,
    show_time: bool = False,
    timezone_id: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    """
    Send report to Slack with conversion analytics.

    Args:
        channel (str): Slack channel to send to (optional, uses env variable if not provided)
        client: Optional Slack client to reuse
        session (Session): Database session
        start_date (datetime | None): Start date for the calculation (in UTC)
        end_date (datetime | None): End date for the calculation (in UTC)
        account_name (str | None): Optional account name to filter by
        show_time (bool): If True, show full datetime with time and timezone in report title
        timezone_id (str | None): Timezone ID to convert UTC times to local time
        timezone_name (str | None): Timezone abbreviation to display

    Returns:
        dict: Status of the operation
    """
    return await _slack.send_report_to_slack(
        slack_channel,
        client,
        session,
        start_date,
        end_date,
        account_name,
        show_time,
        timezone_id,
        timezone_name,
    )


async def handle_slack_events(request):
    """
    Handle Slack events including URL verification and message events.

    Args:
        request: FastAPI Request object

    Returns:
        FastAPI Response object for Slack
    """
    return await _slack.handle_slack_events(request)
