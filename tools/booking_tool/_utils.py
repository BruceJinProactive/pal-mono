import datetime

import pytz  # Add this import


def _convert_to_eastern_time(utc_datetime_str: str) -> tuple[str, str]:
    """
    Convert a UTC datetime string to Eastern Time Zone.

    Args:
        utc_datetime_str (str): The UTC datetime string.

    Returns:
        tuple: The date and time strings converted to Eastern Time Zone.
    """
    utc_datetime = datetime.datetime.strptime(utc_datetime_str, "%Y-%m-%dT%H:%M:%SZ")
    utc_datetime = utc_datetime.replace(tzinfo=pytz.utc)
    eastern = pytz.timezone("US/Eastern")
    eastern_datetime = utc_datetime.astimezone(eastern)
    return eastern_datetime.strftime("%Y-%m-%d"), eastern_datetime.strftime(
        "%H:%M:%S%z"
    )


def _date_in_the_future(session_date_str: str) -> bool:
    """
    Check if the given session date is in the future.

    Args:
        session_date_str (str): The session date string in UTC.

    Returns:
        bool: True if the session date is in the future, False otherwise.
    """
    curr_date = datetime.datetime.now(datetime.timezone.utc)
    session_date = datetime.datetime.strptime(
        session_date_str, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=datetime.timezone.utc)

    return curr_date < session_date
