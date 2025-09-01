from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool
from tools.minitable_tool._apis import create_reservation, suggest_availability
from tools.minitable_tool.phone_number_validator import validate_and_format_phone
from utils.log import logger


class MiniTableTool(Toolkit, BaseReservationTool):
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

    @tool
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check availability for restaurant reservations.

        Args:
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format (e.g., "2024-03-15")
            time: Time for the reservation in HH:MM format (24-hour, e.g., "19:30", "12:00")
        """

        try:
            requested_datetime_string = f"{date} {time}"

            logger.debug(
                f"[MiniTable] Checking availability for party_size: {party_size}, requested_time: {requested_datetime_string}"
            )

            result = suggest_availability(
                restaurant_id=self.restaurant_id,
                party_size=party_size,
                start_sec=requested_datetime_string,
                duration_sec=1800,  # 30 minutes default
            )

            slot_time_availability = result.get("slot_time_availability", {})
            suggest_slot_times = result.get("suggest_slot_time", [])

            is_available = slot_time_availability.get("available", False)

            if is_available:
                # If available, no suggestions are returned according to API spec
                return f"Great! Your requested time {requested_datetime_string} is available."
            else:
                if suggest_slot_times:
                    # API returns max 2 suggested times within the hour before or after
                    suggestions = [slot.get("start_sec") for slot in suggest_slot_times]
                    suggestions_str = ", ".join(suggestions)
                    return f"Your requested time {requested_datetime_string} is not available. Here are nearby available times: {suggestions_str}"
                else:
                    return f"Sorry, no available time slots found near {requested_datetime_string}."

        except Exception as e:
            logger.error(f"[MiniTable] Error checking availability: {str(e)}")
            return f"Error checking availability: {str(e)}"

    @tool
    def make_reservation(  # type: ignore[misc]
        self,
        phone: str,
        first_name: str,
        last_name: str,
        email: str,
        party_size: int,
        date: str,
        time: str,
        notes: str = "",
    ) -> str:
        """
        Make a reservation at the restaurant.

        Args:
            phone: Customer phone number in xxx-xxx-xxxx format (e.g., "123-456-7890")
            first_name: Customer first name
            last_name: Customer last name
            email: Customer email address
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format (e.g., "2024-03-15")
            time: Time for the reservation in HH:MM format (24-hour, e.g., "19:30", "12:00")
            notes: Optional notes for the reservation
        """
        customer_name = f"{first_name} {last_name}"
        logger.debug(
            f"[MiniTable] Making reservation for {customer_name}, party_size: {party_size}, date: {date}, time: {time}"
        )

        try:
            # Validate and format phone number
            formatted_telephone = validate_and_format_phone(phone)

            reservation_params = {
                "telephone": formatted_telephone,
                "customer_name": customer_name,
                "start_sec": f"{date} {time}",
                "party_size": party_size,
                "note": notes,
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

    @tool
    def get_waitlist_status(self, **kwargs) -> str:  # type: ignore[misc]
        """
        Get current waitlist status and wait times for the restaurant.

        Note: MiniTable does not currently support waitlist functionality.
        """
        return "Waitlist functionality is not supported by MiniTable at this time."

    @tool
    def join_waitlist_queue(  # type: ignore[misc]
        self,
        first_name: str,
        last_name: str,
        phone: str,
        party_size: int,
        notes: str = "",
        **kwargs,
    ) -> str:
        """
        Join the waitlist queue for the restaurant.

        Note: MiniTable does not currently support waitlist functionality.
        """
        return "Waitlist functionality is not supported by MiniTable at this time."
