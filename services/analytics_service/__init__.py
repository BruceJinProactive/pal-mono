import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.admin.analytics import Event as AnalyticsEvent

from . import _implementation


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


def get_report_from_mixpanel(
    report_name: str, account_name: str, start_date: datetime, end_date: datetime
) -> dict | None:
    """Fetches insights data from Mixpanel for a given report name and account name.

    Args:
        report_name (str): The name of the report, used to fetch the corresponding bookmark ID.
        account_name (str): The name of the account to filter the report data.

    Returns:
        dict | None: The report data from Mixpanel.
    """
    return _implementation.get_report_from_mixpanel(
        report_name, account_name, start_date, end_date
    )


def get_all_reports_from_mixpanel(
    account_name: str,
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[str, dict]]:
    """
    Fetches all insights data from Mixpanel for all reports defined in BOOKMARK_ID_MAPPING.

    Args:
        account_name (str): The name of the account to fetch the report data.
        start_date (datetime): Start date for the report data.
        end_date (datetime): End date for the report data.

    Returns:
        list[tuple[str, dict]]: A list of tuples containing report names and their data.
    """
    return _implementation.get_all_reports_from_mixpanel(
        account_name, start_date, end_date
    )


async def get_DAU(
    session: AsyncSession,
    account_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict[str, int]]:
    """
    Calculate Daily Active Users (DAU) for a given account within a date range (async version).

    Args:
        session (AsyncSession): Async database session
        account_id (uuid.UUID): The account ID to calculate DAU for
        start_date (datetime): Start date for the DAU calculation
        end_date (datetime): End date for the DAU calculation

    Returns:
        dict[str, dict[str, int]]: Dictionary with date strings as keys and channel DAU counts as values
    """
    return await _implementation.get_DAU(session, account_id, start_date, end_date)


async def get_daily_message_turns(
    session: AsyncSession,
    account_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict[str, int]]:
    """
    Calculate Daily Message Turns for a given account within a date range.

    A "turn" consists of a user message followed by an agent response.
    We count agent messages since each represents a completed conversation turn.

    Args:
        session (AsyncSession): Async database session
        account_id (uuid.UUID): The account ID to calculate message turns for
        start_date (datetime): Start date for the calculation
        end_date (datetime): End date for the calculation

    Returns:
        dict[str, dict[str, int]]: Dictionary with date strings as keys and channel turn counts as values
    """
    return await _implementation.get_daily_message_turns(
        session, account_id, start_date, end_date
    )
