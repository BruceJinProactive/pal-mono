import asyncio
import os
from datetime import datetime

import requests
from mixpanel import Mixpanel

from api.schemas.admin.analytics import Event as AnalyticsEvent
from utils.log import logger

MIXPANEL_BASE_URL = "https://mixpanel.com/api"
MIXPANEL_PROJECT_ID = 3584752
MIXPANEL_WORKSPACE_ID = 9701744

# New mapping
EVENT_NAME_MAPPING = {
    "DAU": "Page View",
    "MAU": "Page View",
    "MESSAGE": "Message Sent",
    "CONVERSION": "Checkout Complete",
}

# Add interval mapping for each report type
REPORT_INTERVAL_MAPPING = {
    "DAU": "day",
    "MAU": "month",
    "MESSAGE": "day",
    "CONVERSION": "day",
}

RAW_MIXPANEL_REPORTS = [
    # (event_name, report_title, interval)
    ("Page View", "Daily Active Users", "day"),
    ("Page View", "Monthly Active Users", "month"),
    ("Message Sent", "Turn of Messages", "day"),
    ("Checkout Complete", "Checkout Conversion", "day"),
]


def get_report_from_mixpanel(
    report_name: str, account_name: str, start_date: datetime, end_date: datetime
) -> dict | None:
    """Fetches report data from Mixpanel using the raw insights API.

    Args:
        report_name (str): The name of the report, used to fetch the corresponding event name.
        account_name (str): The name of the account to filter the report data.
        start_date (datetime): Start of the date range.
        end_date (datetime): End of the date range.

    Returns:
        dict|None: The report data from Mixpanel, or None if the request fails.
    """
    report_name = report_name.upper()
    event_name = EVENT_NAME_MAPPING.get(report_name)
    if not event_name:
        raise ValueError(
            f"Event name mapping not found for report name '{report_name}'"
        )
    interval = REPORT_INTERVAL_MAPPING.get(report_name, "day")

    return get_raw_insights_report(
        event_name, account_name, start_date, end_date, interval=interval
    )


def get_raw_insights_report(
    event_name: str,
    account_name: str,
    start_date: datetime,
    end_date: datetime,
    aggregation_type: str = "unique",
    group_by: str = 'properties["account"]',
    interval: str = "day",  # Accepts "day", "month", etc.
) -> dict | None:
    mixpanel_api_secret = os.getenv("MIXPANEL_API_SECRET")
    if not mixpanel_api_secret:
        raise ValueError("Environment variable MIXPANEL_API_SECRET is not set.")

    safe_account_name = account_name.replace('"', '\\"')

    params = {
        "project_id": MIXPANEL_PROJECT_ID,
        "from_date": start_date.strftime("%Y-%m-%d"),
        "to_date": end_date.strftime("%Y-%m-%d"),
        "event": event_name,
        "type": aggregation_type,
        "on": group_by,
        "interval": interval,
        "where": f'properties["account"] == "{safe_account_name}"',
    }

    headers = {"Accept": "application/json"}

    try:
        response = requests.get(
            url=f"{MIXPANEL_BASE_URL}/2.0/insights",
            params=params,
            headers=headers,
            auth=(mixpanel_api_secret, ""),
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Failed to fetch raw insights for event '{event_name}' and account '{account_name}': {e}"
        )
        return None


def get_all_reports_from_mixpanel(
    account_name: str,
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[str, dict]]:
    results = []
    for event_name, report_title, interval in RAW_MIXPANEL_REPORTS:
        report_data = get_raw_insights_report(
            event_name, account_name, start_date, end_date, interval=interval
        )
        if report_data:
            results.append((report_title, report_data))
    return results


def track_event(user_id: str, event_name: AnalyticsEvent, event_properties: dict):
    def _track():
        try:
            MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
            mp = None
            if MIXPANEL_PROJECT_TOKEN:
                mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)
            if mp:
                runtime_env = os.getenv("RUNTIME_ENV", "dev")
                event_properties["runtime_env"] = runtime_env
                mp.track(user_id, event_name, event_properties)
        except Exception as e:
            logger.error(f"Error tracking event {event_name} for user {user_id}: {e}")

    asyncio.create_task(asyncio.to_thread(_track))
