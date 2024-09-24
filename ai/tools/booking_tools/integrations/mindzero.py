import datetime
import json

import httpx


class MindZeroIntegration:
    def book_a_class(self) -> str:
        """Use this function to book a class session.

        Returns:
            str: JSON string of class session booking status.
        """
        return "Please contact a sales representative to book a class session."

    def get_classes(self, num_days: int = 7) -> str:
        """Use this function to answer any questions regarding class session availability.

        Args:
            num_days (int): Number of days in advance to look for. Defaults to 7 if user doesn't supply.

        Returns:
            str: JSON string of class session availability.
        """
        # Date range to search within: [Today, Today+num_days]
        min_date = datetime.datetime.today().strftime("%Y-%m-%d")
        max_date = datetime.date.today() + datetime.timedelta(days=num_days)

        response = httpx.get(
            f"https://mindzero.marianatek.com/api/class_sessions?include=employee_public_profiles%2Clayout%2Ctags&location=48717&max_date={max_date}&min_date={min_date}&ordering=start_datetime&page_size=20"
        )
        data = response.json()["data"]

        # Returns whether the session is in the future (True) or not (False)
        def date_in_the_future(session_date_str):
            curr_date = datetime.datetime.now(datetime.timezone.utc)
            session_date = datetime.datetime.strptime(
                session_date_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)

            return curr_date < session_date

        # Filter through the API response to gather and reformat desired data.
        result = []
        for entry in data:
            # Filter out sessions in past.
            if date_in_the_future(entry["attributes"]["start_datetime"]):
                new_entry = {}
                new_entry["start_date"] = entry["attributes"]["start_date"]
                new_entry["start_time"] = entry["attributes"]["start_time"]
                new_entry["class_id"] = entry["id"]
                new_entry["available_spots_count"] = len(
                    entry["attributes"]["available_spots"]
                )
                new_entry["class_type"] = entry["attributes"]["class_type_display"]
                new_entry["duration"] = entry["attributes"]["duration"]
                new_entry["instructor"] = entry["attributes"]["instructor_names"]
                result.append(new_entry)

        return json.dumps(result)
