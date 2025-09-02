import asyncio
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from api.schemas.admin.analytics import Event as AnalyticsEvent
from api.schemas.admin.analytics import GetAllReportsResponse

from . import _implementation, _slack


# BRUCETODO: DELETE - Mixpanel related functions after migration to db
def track_event(user_id: str, event_name: AnalyticsEvent, event_properties: dict):
    """
    Track an event in Mixpanel.

    Args:
        user_id (str): The unique identifier of the user.
        event_name (AnalyticsEvent): The name of the event to track.
        event_properties (dict): The properties of the event to track.

    Returns:
        None
    """
    return _implementation.track_event(user_id, event_name, event_properties)


async def get_account_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,  # ← Add this missing parameter
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Get both Active Users and Message Turns analytics data for a given account within a date range.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime): Start date for the calculation
        end_date (datetime): End date for the calculation
        group_by (list[str] | None): List of fields to group by  # ← Add this to docstring
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    return await asyncio.to_thread(
        _implementation.get_account_reports,
        session,
        account_id,
        start_date,
        end_date,
        group_by=group_by,
        filter_by=filter_by,
    )


async def send_daily_report_to_slack(channel: str | None = None, client=None) -> dict:
    """
    Send a comprehensive daily commerce report to Slack with conversion analytics.

    Args:
        channel (str): Slack channel to send to (optional, uses env variable if not provided)
        client: Optional Slack client to reuse
        session (AsyncSession): Async database session for fetching conversion data

    Returns:
        dict: Status of the operation
    """
    return await _slack.send_daily_report_to_slack(channel, client)


async def handle_slack_events(request):
    """
    Handle Slack events including URL verification and message events.

    Args:
        request: FastAPI Request object

    Returns:
        FastAPI Response object for Slack
    """
    return await _slack.handle_slack_events(request)
