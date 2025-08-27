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


def get_analytics_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> GetAllReportsResponse:
    """
    Get both DAU and Message Turns analytics data for a given account within a date range.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime): Start date for the calculation
        end_date (datetime): End date for the calculation

    Returns:
        dict[str, AnalyticsResponse]: Dictionary with report names as keys and analytics data as values
    """
    return _implementation.get_analytics_reports(
        session, account_id, start_date, end_date
    )


async def send_daily_report_to_slack(
    channel: str | None = None, client=None, session: AsyncSession | None = None
) -> dict:
    """
    Send a comprehensive daily commerce report to Slack with conversion analytics.

    Args:
        channel (str): Slack channel to send to (optional, uses env variable if not provided)
        client: Optional Slack client to reuse
        session (AsyncSession): Async database session for fetching conversion data

    Returns:
        dict: Status of the operation
    """
    return await _slack.send_daily_report_to_slack(channel, client, session)


async def handle_slack_events(request):
    """
    Handle Slack events including URL verification and message events.

    Args:
        request: FastAPI Request object

    Returns:
        FastAPI Response object for Slack
    """
    return await _slack.handle_slack_events(request)


def get_all_accounts_conversion_stats(
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """
    Get conversion statistics for all accounts with date filtering.
    Always includes a TOTAL row with aggregated data.

    Args:
        session: Database session (must be Session)
        start_date: Optional start date for filtering (converted to UTC)
        end_date: Optional end date for filtering (converted to UTC)

    Returns:
        list[dict]: List of conversion statistics for all accounts (includes TOTAL row)
    """
    return _implementation.get_all_accounts_conversion_stats(
        session, start_date, end_date
    )


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
    return _implementation.get_account_conversion_stats(
        session, account_id, start_date, end_date
    )
