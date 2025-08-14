import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from api.schemas.admin.analytics import Event as AnalyticsEvent
from api.schemas.admin.analytics import GetAllReportsResponse

from . import _implementation


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
