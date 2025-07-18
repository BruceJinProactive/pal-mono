import asyncio
import os
import uuid
from datetime import datetime

import requests
from mixpanel import Mixpanel
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.admin.analytics import Event as AnalyticsEvent
from utils.log import logger

MIXPANEL_BASE_URL = "https://mixpanel.com/api"
MIXPANEL_PROJECT_ID = 3584752
MIXPANEL_WORKSPACE_ID = 9701744

# Mapping of report names to bookmark IDs, will store them in db in the future
BOOKMARK_ID_MAPPING = {
    "ORDER": 81979859,
}

MIXPANEL_REPORTS = [
    (81979859, "Total Order Value"),
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


async def get_DAU(
    session: AsyncSession,
    account_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict[str, int]]:
    """
    Calculate Daily Active Users (DAU) for a given account within a date range.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate DAU for
        start_date (datetime): Start date for the DAU calculation
        end_date (datetime): End date for the DAU calculation

    Returns:
        dict[str, dict[str, int]]: Dictionary with date strings as keys and channel DAU counts as values
    """
    try:
        message_repo = db.MessageRepositoryAsync(session)
        result = await message_repo.get_daily_active_users(
            account_id, start_date, end_date
        )
        return result
    except Exception as e:
        logger.error(f"Error calculating DAU for account {account_id}: {e}")
        logger.exception("Full DAU exception traceback:")
        return {}


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
    try:
        message_repo = db.MessageRepositoryAsync(session)
        result = await message_repo.get_daily_message_turns(
            account_id, start_date, end_date
        )
        return result
    except Exception as e:
        logger.error(f"Error calculating message turns for account {account_id}: {e}")
        logger.exception("Full message turns exception traceback:")
        return {}
