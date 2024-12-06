import datetime
import json

import httpx
import pytz  # Add this import

from utils.log import logger


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


class MindZeroIntegration:
    def book_a_class(self) -> str:
        """
        Use this function to book a class.

        Returns:
            str: JSON string of class session booking status.
        """
        return "Please contact a sales representative to book a class session."

    def get_classes(self, num_days: int) -> str:
        """
        Use this function to answer any questions regarding class session availability.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class session availability.
        """
        # Date range to search within: [Today, Today+num_days]
        min_date = datetime.datetime.today().strftime("%Y-%m-%d")
        max_date = datetime.date.today() + datetime.timedelta(days=num_days)
        try:
            response = httpx.get(
                f"https://mindzero.marianatek.com/api/class_sessions?include=employee_public_profiles%2Clayout%2Ctags&location=48717&max_date={max_date}&min_date={min_date}&ordering=start_datetime&page_size=20"
            )
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json().get("data", [])

        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
            logger.error(f"[MindZeroIntegration.get_classes] Error occurred: {e}")
            return (
                "The class scheduler is currently unavailable. Please try again later."
            )

        # Filter through the API response to gather and reformat desired data.
        result = []
        for entry in data:
            # Filter out sessions in past.
            if _date_in_the_future(entry["attributes"]["start_datetime"]):
                new_entry = {}
                new_entry["start_date"], new_entry["start_time"] = (
                    _convert_to_eastern_time(entry["attributes"]["start_datetime"])
                )
                new_entry["class_id"] = entry["id"]
                new_entry["available_spots_count"] = len(
                    entry["attributes"]["available_spots"]
                )
                new_entry["class_type"] = entry["attributes"]["class_type_display"]
                new_entry["duration"] = entry["attributes"]["duration"]
                new_entry["instructor"] = entry["attributes"]["instructor_names"]
                result.append(new_entry)

        return json.dumps(result)
