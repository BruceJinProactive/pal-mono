from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.minitable_tool._apis import search_availability as search_availability_api
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
            from datetime import datetime

            # Convert target_time to Unix timestamp
            dt = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
            start_sec = int(dt.timestamp())

            search_params = {
                "party_size": party_size,
                "start_sec": start_sec,
                "duration_sec": 3600,
            }

            # Call the API
            result = search_availability_api(
                restaurant_id=self.restaurant_id,
                search_params=search_params,
            )

            slot_time_availability = result.get("slot_time_availability", [])
            available_slots = [
                slot for slot in slot_time_availability if slot.get("available")
            ]
            return f"Available times found: {len(available_slots)} slots - {available_slots}"

        except Exception as e:
            logger.error(f"[MiniTable] Error checking availability: {str(e)}")
            return f"Error checking availability: {str(e)}"

    @tool
    def make_reservation(self) -> str:
        """
        Make a reservation at the restaurant.
        """
        # TODO: Implement reservation creation logic
        return "MiniTable reservation creation - implementation pending"
