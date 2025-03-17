import datetime
import json

import httpx
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from utils.log import logger

from . import _utils

MINDZERO_CLASS_URL = "https://mindzero.marianatek.com/api/class_sessions?include=employee_public_profiles%2Clayout%2Ctags&location={location_id}&max_date={max_date}&min_date={min_date}&ordering=start_datetime&page_size=20"


class BookingTool(Toolkit):

    def __init__(self, location_id: str):
        super().__init__(name="booking_tools")

        # Register tools
        self.register(self.book_a_class)
        self.register(self.get_classes)

        # Configs
        self.location_id = location_id

    @tool
    def book_a_class(self) -> str:
        """
        Use this function to book a class.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class availability.
        """
        return "Please contact a sales representative to book a class session!"

    @tool
    def get_classes(self, num_days: int) -> str:
        """
        Use this function to answer any questions regarding class session availability.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class session availability.
        """
        # TODO: right now BookingTools is overfitted to MindZero
        # We want to make booking tools more generic

        # Date range to search within: [Today, Today+num_days]
        min_date = datetime.datetime.today().strftime("%Y-%m-%d")
        max_date = datetime.date.today() + datetime.timedelta(days=num_days)
        try:
            response = httpx.get(
                MINDZERO_CLASS_URL.format(
                    location_id=self.location_id, max_date=max_date, min_date=min_date
                )
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
            if _utils._date_in_the_future(entry["attributes"]["start_datetime"]):
                new_entry = {}
                new_entry["start_date"], new_entry["start_time"] = (
                    _utils._convert_to_eastern_time(
                        entry["attributes"]["start_datetime"]
                    )
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
