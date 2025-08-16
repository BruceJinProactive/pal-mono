from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata


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
    def check_availability(self) -> str:
        """
        Check availability for restaurant reservations.
        """
        # TODO: Implement availability check logic
        return "MiniTable availability check - implementation pending"

    @tool
    def make_reservation(self) -> str:
        """
        Make a reservation at the restaurant.
        """
        # TODO: Implement reservation creation logic
        return "MiniTable reservation creation - implementation pending"
