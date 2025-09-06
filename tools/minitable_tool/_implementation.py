from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool, params_validate
from tools.minitable_tool._apis import (
    check_waitlist_status,
    create_reservation,
    create_waitlist,
    suggest_availability,
)
from tools.minitable_tool.phone_number_validator import validate_and_format_phone
from utils.log import logger


class MiniTableTool(Toolkit, BaseReservationTool):
    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = [
        "phone",
        "first_name",
        "last_name",
        "party_size",
        "date",
        "time",
    ]
    REQUIRED_JOIN_WAITLIST_QUEUE_FIELDS = [
        "first_name",
        "last_name",
        "phone",
        "party_size",
    ]

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
        self.register(self.get_waitlist_status)
        self.register(self.join_waitlist_queue)

    @tool
    @params_validate()
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
    @params_validate()
    def make_reservation(  # type: ignore[misc]
        self,
        phone: str,
        first_name: str,
        party_size: int,
        date: str,
        time: str,
        last_name: str,
        email: str = "",
        notes: str = "",
    ) -> str:
        """
        Make a reservation at the restaurant.

        Args:
            phone: Customer phone number in xxx-xxx-xxxx format (e.g., "123-456-7890")
            first_name: Customer first name
            last_name: Customer last name
            email: Customer email address (optional)
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
    def get_waitlist_status(self) -> str:  # type: ignore[misc]
        """
        Get current waitlist status and wait times for the restaurant.
        """
        try:
            logger.debug(
                f"[MiniTable] Getting waitlist status for restaurant {self.restaurant_id}"
            )

            result = check_waitlist_status(merchant_id=str(self.restaurant_id))

            status = result.get("status", "Unknown")
            reason = result.get("reason", "")
            wait_estimate = result.get("wait_estimate", {})

            if status == "Closed":
                return f"Waitlist is currently closed. {reason}".strip()

            if status == "Open":
                response_parts = ["Waitlist is currently open."]

                if wait_estimate:
                    response_parts.append("Current wait estimates by party size:")

                    # Format wait estimates for different party sizes
                    for category, info in wait_estimate.items():
                        parties_ahead = info.get("parties_ahead_count", 0)
                        from_size = info.get("from_people_number", 0)
                        to_size = info.get("to_people_number", 0)

                        if to_size == 9999:
                            size_range = f"{from_size}+ people"
                        else:
                            size_range = f"{from_size}-{to_size} people"

                        response_parts.append(
                            f"- {size_range}: {parties_ahead} parties ahead"
                        )

                return "\n".join(response_parts)

            return f"Waitlist status: {status}. {reason}".strip()

        except Exception as e:
            logger.error(f"[MiniTable] Error getting waitlist status: {str(e)}")
            return f"Error getting waitlist status: {str(e)}"

    @tool
    @params_validate()
    def join_waitlist_queue(  # type: ignore[misc]
        self,
        first_name: str,
        last_name: str,
        phone: str,
        party_size: int,
        notes: str = "",
    ) -> str:
        """
        Join the waitlist queue for the restaurant.

        Args:
            first_name: Customer first name
            last_name: Customer last name
            phone: Customer phone number
            party_size: Number of people in the party
            notes: Optional notes for the waitlist entry
        """
        customer_name = f"{first_name} {last_name}"
        logger.debug(
            f"[MiniTable] Adding to waitlist: {customer_name}, party_size: {party_size}"
        )

        try:
            # Validate and format phone number
            formatted_telephone = validate_and_format_phone(phone)

            result = create_waitlist(
                merchant_id=str(self.restaurant_id),
                party_size=party_size,
                telephone=formatted_telephone,
                customer_name=customer_name,
                note=notes,
            )

            # Check for business logic failures
            business_failure = result.get("waitlist_business_logic_failure")
            if business_failure:
                cause = business_failure.get("cause", "Unknown")
                description = business_failure.get("description", "")

                if cause == "EXISTING_WAITLIST_ENTRY":
                    return "You already have an entry on the waitlist."
                elif cause == "WAITLIST_FULL":
                    return "The waitlist is currently full. Please try again later."
                elif cause == "WAITLIST_NOT_ENABLE":
                    return "The waitlist is not currently enabled for this restaurant."
                else:
                    return (
                        f"Unable to join waitlist: {description}"
                        if description
                        else f"Unable to join waitlist due to: {cause}"
                    )

            # Success case
            waitlist_id = result.get("waitlist_id")
            wait_code = result.get("wait_code")
            left_count = result.get("left_count", 0)

            if waitlist_id and wait_code:
                return f"Successfully added to waitlist! Waitlist ID: {waitlist_id}, Wait code: {wait_code}, Position: {left_count + 1} parties ahead of you."
            else:
                return "Successfully added to waitlist, but some details are missing from the response."

        except ValueError as e:
            error_msg = str(e)
            # Handle phone number validation errors specifically
            if "phone number" in error_msg.lower():
                return f"{error_msg}. Please provide a valid US phone number."
            return f"Validation error: {error_msg}"
        except Exception as e:
            logger.error(f"[MiniTable] Error joining waitlist: {str(e)}")
            return f"Error joining waitlist: {str(e)}"
