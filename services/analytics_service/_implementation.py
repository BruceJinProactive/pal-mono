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

# Mapping of report names to bookmark IDs, will store them in db in the future
BOOKMARK_ID_MAPPING = {
    "DAU": 76662037,
    "MAU": 76661239,
    "MESSAGE": 76661240,
    "CONVERSION": 76661919,
}

MIXPANEL_REPORTS = [
    (76662037, "Daily Active Users"),
    (76661239, "Monthly Active Users"),
    (76661240, "Turn of Messages"),
    (76661919, "Checkout Conversion"),
]


def get_report_from_mixpanel(
    report_name: str, account_name: str, start_date: datetime, end_date: datetime
) -> dict | None:
    """Fetches report data from Mixpanel for a given report name and account name.

    Args:
        report_name (str): The name of the report, used to fetch the corresponding bookmark ID.
        account_name (str): The name of the account to filter the report data.

    Returns:
        dict|None: The report data from Mixpanel, or None if the request fails.
    """
    report_name = report_name.upper()
    bookmark_id = BOOKMARK_ID_MAPPING.get(report_name)
    if not bookmark_id:
        raise ValueError(
            f"Environment variable MIXPANEL_{report_name}_BOOKMARK_ID is not set."
        )
    return get_report_by_id(bookmark_id, account_name, start_date, end_date)


def get_report_by_id(
    bookmark_id,
    account_name: str,
    start_date: datetime,
    end_date: datetime,
) -> dict | None:
    mixpanel_api_secret = os.getenv("MIXPANEL_API_SECRET")

    if not mixpanel_api_secret:
        raise ValueError("Environment variable MIXPANEL_API_SECRET is not set.")

    params = {
        "project_id": MIXPANEL_PROJECT_ID,
        "workspace_id": MIXPANEL_WORKSPACE_ID,
        "bookmark_id": bookmark_id,
        "from_date": start_date.strftime("%Y-%m-%d"),
        "to_date": end_date.strftime("%Y-%m-%d"),
    }
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(
            url=f"{MIXPANEL_BASE_URL}/query/insights",
            params=params,
            headers=headers,
            auth=(mixpanel_api_secret, ""),
        )
        response.raise_for_status()  # Raises an HTTPError if the response code is 4xx/5xx

        response_data = response.json().get("series", {})
        series_values = list(response_data.values())

        if series_values:
            account_data = series_values[0].get(account_name, {})
        else:
            account_data = None

        return account_data

    except requests.exceptions.RequestException as e:
        logger.error(
            f"Failed to fetch data from Mixpanel for report id '{bookmark_id}' and account '{account_name}': {e}"
        )
        return None


def get_all_reports_from_mixpanel(
    account_name: str,
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[str, dict]]:
    results = []
    for bookmark_id, report_name in MIXPANEL_REPORTS:
        report_data = get_report_by_id(
            str(bookmark_id), account_name, start_date, end_date
        )
        if not report_data:
            continue
        results.append((report_name, report_data))
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
