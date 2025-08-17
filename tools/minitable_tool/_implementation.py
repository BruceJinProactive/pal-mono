from datetime import datetime
from zoneinfo import ZoneInfo

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.minitable_tool._apis import create_reservation, search_availability
from tools.minitable_tool.phone_number_validator import validate_and_format_phone
from utils.log import logger


class MiniTableTool(Toolkit):
    def __init__(
        self,
        restaurant_id: int,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="minitable_tool")

        self.restaurant_id = restaurant_id
        self.tool_metadata = tool_metadata

        self.register(self.check_availability)
        self.register(self.make_reservation)

    def _convert_datetime_to_timestamp(self, date: str, time: str) -> int:
        """
        Convert date and time to Unix timestamp using timezone from tool_metadata.

        Args:
            date: Date in YYYY-MM-DD format
            time: Time in HH:MM format (24-hour)

        Returns:
            Unix timestamp as integer

        Raises:
            ValueError: If timezone is not available in tool_metadata
        """
        if not self.tool_metadata.timezone:
            raise ValueError(
                "Timezone information is required but not available in tool_metadata"
            )

        tz = ZoneInfo(self.tool_metadata.timezone)
        datetime_str = f"{date} {time}"
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        dt_with_tz = dt.replace(tzinfo=tz)
        return int(dt_with_tz.timestamp())

    def _generate_fuzzy_time_slots(
        self, time: str, slots_before: int = 6, slots_after: int = 6
    ) -> list[str]:
        """
        Generate fuzzy time slots around the requested time in 15-minute intervals.

        Args:
            time: Time in HH:MM format
            slots_before: Number of 15-minute slots to search before requested time
            slots_after: Number of 15-minute slots to search after requested time

        Returns:
            List of time strings in HH:MM format for all time slots to search
        """

        # Parse hour and minute
        hour, minute = map(int, time.split(":"))

        # Round to nearest 15-minute interval
        rounded_minute = (minute // 15) * 15

        time_slots = []

        # Generate slots
        for i in range(-slots_before, slots_after + 1):
            total_minutes = hour * 60 + rounded_minute + (i * 15)

            # Handle day overflow/underflow
            if total_minutes < 0:
                continue  # Skip negative times
            if total_minutes >= 24 * 60:
                continue  # Skip times past midnight

            slot_hour = total_minutes // 60
            slot_minute = total_minutes % 60
            time_slots.append(f"{slot_hour:02d}:{slot_minute:02d}")

        return time_slots

    @tool
    def check_availability(self, party_size: int, date: str, time: str) -> str:
        """
        Check availability for restaurant reservations.

        Args:
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format (e.g., "2024-03-15")
            time: Time for the reservation in HH:MM format (24-hour, e.g., "19:30", "12:00")
        """

        logger.debug(
            f"[MiniTable] Checking availability for party_size: {party_size}, date: {date}, time: {time}"
        )

        try:
            # Generate fuzzy time slots as strings
            fuzzy_time_slots = self._generate_fuzzy_time_slots(time)

            # Convert time slots to timestamps
            fuzzy_timestamps = [
                self._convert_datetime_to_timestamp(date, time_slot)
                for time_slot in fuzzy_time_slots
            ]

            search_params = {
                "party_size": party_size,
                "start_sec_list": fuzzy_timestamps,
                "duration_sec": 3600,
            }

            result = search_availability(
                restaurant_id=self.restaurant_id,
                search_params=search_params,
            )

            slot_time_availability = result.get("slot_time_availability", [])
            available_slots = []
            requested_timestamp = self._convert_datetime_to_timestamp(date, time)
            requested_time_available = False

            for slot in slot_time_availability:
                if slot.get("available"):
                    slot_time = slot.get("slot_time", {})
                    start_sec = slot_time.get("start_sec")

                    # Convert epoch time to local time using timezone
                    if start_sec:
                        if not self.tool_metadata.timezone:
                            raise ValueError(
                                "Timezone information is required but not available in tool_metadata"
                            )
                        tz = ZoneInfo(self.tool_metadata.timezone)
                        dt = datetime.fromtimestamp(int(start_sec), tz=tz)
                        local_time = dt.strftime("%H:%M")

                        # Calculate time difference from requested time
                        time_diff_minutes = (int(start_sec) - requested_timestamp) // 60

                        if time_diff_minutes == 0:
                            requested_time_available = True
                            available_slots.append(
                                {
                                    "time": local_time,
                                    "diff": 0,
                                    "desc": f"{local_time} (requested time)",
                                }
                            )
                        else:
                            if time_diff_minutes > 0:
                                desc = f"{local_time} (+{time_diff_minutes}min)"
                            else:
                                desc = f"{local_time} ({time_diff_minutes}min)"
                            available_slots.append(
                                {
                                    "time": local_time,
                                    "diff": abs(time_diff_minutes),
                                    "desc": desc,
                                }
                            )

            # Check if requested time is available
            if requested_time_available:
                return f"Great! Your requested time {time} is available."
            elif available_slots:
                # Sort by time difference and suggest closest alternatives
                available_slots.sort(key=lambda x: x["diff"])
                suggestions = [
                    slot["desc"] for slot in available_slots[:3]
                ]  # Show up to 3 closest
                return f"Your requested time {time} is not available. Here are the closest available times: {', '.join(suggestions)}"
            else:
                return f"Sorry, no available time slots found for {date} around {time}."

        except Exception as e:
            logger.error(f"[MiniTable] Error checking availability: {str(e)}")
            return f"Error checking availability: {str(e)}"

    @tool
    def make_reservation(
        self,
        telephone: str,
        customer_name: str,
        party_size: int,
        date: str,
        time: str,
        note: str = "",
    ) -> str:
        """
        Make a reservation at the restaurant.

        Args:
            telephone: Customer phone number in xxx-xxx-xxxx format (e.g., "123-456-7890")
            customer_name: Customer name
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format (e.g., "2024-03-15")
            time: Time for the reservation in HH:MM format (24-hour, e.g., "19:30", "12:00")
            note: Optional note for the reservation
        """
        logger.debug(
            f"[MiniTable] Making reservation for {customer_name}, party_size: {party_size}, date: {date}, time: {time}"
        )

        try:
            # Validate and format phone number
            formatted_telephone = validate_and_format_phone(telephone)

            start_sec = self._convert_datetime_to_timestamp(date, time)

            reservation_params = {
                "telephone": formatted_telephone,
                "customer_name": customer_name,
                "start_sec": start_sec,
                "party_size": party_size,
                "note": note,
                "duration_sec": 3600,
            }

            result = create_reservation(
                restaurant_id=self.restaurant_id,
                reservation_params=reservation_params,
            )

            booking = result.get("booking", {})

            if not booking:
                return "Error: No booking information returned from API"

            booking_id = booking.get("booking_id")
            status = booking.get("status")

            if not booking_id or not status:
                return f"Error: Incomplete booking response - booking_id: {booking_id}, status: {status}"

            return f"Reservation created: booking_id={booking_id}, status={status}"

        except ValueError as e:
            error_msg = str(e)
            # Handle phone number validation errors specifically
            if "phone number" in error_msg.lower():
                return f"{error_msg}. Please provide a valid US phone number."
            return f"Validation error: {error_msg}"
        except Exception as e:
            logger.error(f"[MiniTable] Error creating reservation: {str(e)}")
            return f"Error creating reservation: {str(e)}"
