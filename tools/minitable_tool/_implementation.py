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

        try:
            fuzzy_time_slots = self._generate_fuzzy_time_slots(time)
            fuzzy_datetime_strings = [
                f"{date} {time_slot}" for time_slot in fuzzy_time_slots
            ]

            logger.debug(
                f"[MiniTable] Checking availability for party_size: {party_size}, date: {date}, time: {time}, fuzzy_time: {fuzzy_time_slots}"
            )

            search_params = {
                "party_size": party_size,
                "start_sec_list": fuzzy_datetime_strings,
                "duration_sec": 3600,
            }

            result = search_availability(
                restaurant_id=self.restaurant_id,
                search_params=search_params,
            )

            slot_time_availability = result.get("slot_time_availability", [])

            available_start_times = [
                slot.get("slot_time", {}).get("start_sec")
                for slot in slot_time_availability
                if slot.get("available") is True
                and slot.get("slot_time", {}).get("start_sec")
            ]

            requested_datetime_string = f"{date} {time}"

            suggestions = [
                f"{start_time}"
                for start_time in available_start_times[:3]
                if start_time != requested_datetime_string
            ]

            if requested_datetime_string in available_start_times:
                if suggestions:
                    return f"Great! Your requested time {date} {time} is available. Here are all other available times: {', '.join(suggestions)}"
                else:
                    return f"Great! Your requested time {date} {time} is available."
            elif suggestions:
                # Show up to 3 available times
                return f"Your requested time {date} {time} is not available. Here are available times: {', '.join(suggestions)}"
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

            reservation_params = {
                "telephone": formatted_telephone,
                "customer_name": customer_name,
                "start_sec": f"{date} {time}",
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
