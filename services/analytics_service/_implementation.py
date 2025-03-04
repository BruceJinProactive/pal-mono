import os

import requests
from mixpanel import Mixpanel

from api.schemas.admin.analytics import Event as AnalyticsEvent
from utils.log import logger

MIXPANEL_BASE_URL = "https://mixpanel.com/api/query/insights"


def get_report_from_mixpanel(report_name: str, account_name: str) -> dict | None:
    """Fetches report data from Mixpanel for a given report name and account name.

    Args:
        report_name (str): The name of the report, used to fetch the corresponding bookmark ID.
        account_name (str): The name of the account to filter the report data.

    Returns:
        dict|None: The report data from Mixpanel, or None if the request fails.
    """
    mixpanel_api_secret = os.getenv("MIXPANEL_API_SECRET")
    report_name = report_name.upper()
    # Mapping of report names to bookmark IDs, will store them in db in the future
    BOOKMARK_ID_MAPPING = {"MAU": "73277452", "MESSAGE": "73277513"}
    bookmark_id = BOOKMARK_ID_MAPPING.get(report_name)

    if not mixpanel_api_secret:
        raise ValueError("Environment variable MIXPANEL_API_SECRET is not set.")
    if not bookmark_id:
        raise ValueError(
            f"Environment variable MIXPANEL_{report_name}_BOOKMARK_ID is not set."
        )

    url = f"{MIXPANEL_BASE_URL}?project_id=3584752&workspace_id=9298649&bookmark_id={bookmark_id}"
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, auth=(mixpanel_api_secret, ""))
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
            f"Failed to fetch data from Mixpanel for report '{report_name}' and account '{account_name}': {e}"
        )
        return None


def track_event(user_id: str, event_name: AnalyticsEvent, event_properties: dict):
    MIXPANEL_PROJECT_TOKEN = os.getenv("MIXPANEL_PROJECT_TOKEN")
    mp = None
    if MIXPANEL_PROJECT_TOKEN:
        mp = Mixpanel(MIXPANEL_PROJECT_TOKEN)

    if mp:
        runtime_env = os.getenv("RUNTIME_ENV", "dev")
        event_properties["runtime_env"] = runtime_env
        mp.track(user_id, event_name, event_properties)
