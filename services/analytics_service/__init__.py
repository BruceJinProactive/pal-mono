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


def get_report_from_mixpanel(report_name: str, account_name: str) -> dict | None:
    """Fetches insights data from Mixpanel for a given report name and account name.

    Args:
        report_name (str): The name of the report, used to fetch the corresponding bookmark ID.
        account_name (str): The name of the account to filter the report data.

    Returns:
        dict | None: The report data from Mixpanel.
    """
    return _implementation.get_report_from_mixpanel(report_name, account_name)
