from datetime import datetime, timezone

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.minitable_tool._apis import create_reservation, search_availability
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

    @tool
    def check_availability(self, party_size: int, target_time: str) -> str:
        """
        Check availability for restaurant reservations.

        Args:
            party_size: Number of people for the reservation
            target_time: Target date and time for the reservation (ISO 8601 format)
        """

        logger.debug(
            f"[MiniTable] Checking availability for party_size: {party_size}, target_time: {target_time}"
        )

        try:

            # Convert target_time to Unix timestamp
            dt = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
            start_sec = int(dt.timestamp())

            search_params = {
                "party_size": party_size,
                "start_sec": start_sec,
                "duration_sec": 3600,
            }

            result = search_availability(
                restaurant_id=self.restaurant_id,
                search_params=search_params,
            )

            slot_time_availability = result.get("slot_time_availability", [])
            available_slots = []

            for slot in slot_time_availability:
                if slot.get("available"):
                    slot_time = slot.get("slot_time", {})
                    start_sec = slot_time.get("start_sec")
                    duration_sec = slot_time.get("duration_sec")

                    # Convert epoch time to UTC datetime string
                    if start_sec:
                        dt = datetime.fromtimestamp(int(start_sec), tz=timezone.utc)
                        utc_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        available_slots.append(
                            {
                                "time": utc_time,
                                "duration_sec": duration_sec,
                            }
                        )

            return f"Available times found: {len(available_slots)} slots - {available_slots}"

        except Exception as e:
            logger.error(f"[MiniTable] Error checking availability: {str(e)}")
            return f"Error checking availability: {str(e)}"

    @tool
    def make_reservation(
        self,
        telephone: str,
        customer_name: str,
        party_size: int,
        target_time: str,
        note: str = "",
    ) -> str:
        """
        Make a reservation at the restaurant.

        Args:
            telephone: Customer phone number
            customer_name: Customer name
            party_size: Number of people for the reservation
            target_time: Target date and time for the reservation (ISO 8601 format)
            note: Optional note for the reservation
        """
        logger.debug(
            f"[MiniTable] Making reservation for {customer_name}, party_size: {party_size}, target_time: {target_time}"
        )

        try:
            # Convert target_time to Unix timestamp
            dt = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
            start_sec = int(dt.timestamp())

            reservation_params = {
                "telephone": telephone,
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

        except Exception as e:
            logger.error(f"[MiniTable] Error creating reservation: {str(e)}")
            return f"Error creating reservation: {str(e)}"
