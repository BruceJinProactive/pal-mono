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


def get_all_reports_from_mixpanel(account_name: str) -> list[tuple[str, dict]]:
    """
    Fetches all available reports for the given account name.

    Args:
        account_name (str): The name of the account to fetch the report data.

    Returns:
        list[tuple[str, dict]]: The report data from Mixpanel where each tuple contains
        the report name and the report data.
    """
    return _implementation.get_all_reports_from_mixpanel(account_name)
