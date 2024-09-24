from typing import Optional

from phi.tools import Toolkit

from ai.tools.booking_tools.integrations.mindzero import MindZeroIntegration


class BookingTools(Toolkit):
    def __str__(self):
        return "BookingTools"

    def __init__(self, config: dict):
        super().__init__(name="booking_tools")

        # Tool configuration
        self.api_key = config.get("api_key", None)
        self.api_secret = config.get("api_secret", None)

        # Tool actions
        self.register(self.get_classes)
        self.register(self.book_a_class)

        # Tool integrations
        # TODO: create a tool integration module
        self.integration_map = {
            "mindzero": MindZeroIntegration,
            # Add other integrations here
        }
        integration_class = self.integration_map.get(config["type"])

        if not integration_class:
            raise ValueError(f"Unknown integration type: {config['type']}")

        # Lazy load integration
        self.integration = integration_class()

    def get_classes(self, num_days: Optional[int]) -> str:
        """Use this function to answer any questions regarding class availability.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class availability.
        """
        return self.integration.get_classes(num_days)

    def book_a_class(self) -> str:
        """Use this function to answer any questions regarding class availability.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class availability.
        """
        return self.integration.book_a_class()
