from phi.tools.toolkit import Toolkit

from ai.tools.booking_tools.integrations.mindzero import MindZeroIntegration


class BookingTools(Toolkit):
    def __str__(self):
        return "BookingTools"

    def __init__(self, config: dict, user_id: str):
        super().__init__(name="booking_tools")

        # Toolkit tools (actions)
        self.register(self.book_a_class)
        self.register(self.get_classes)

        # Toolkit configuration
        self.api_key = config.get("api_key", None)
        self.api_secret = config.get("api_secret", None)

        # Toolkit integrations
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

    # ----------------------------------------
    # Toolkit tools (actions)
    # ----------------------------------------

    def book_a_class(self) -> str:
        """Use this function to answer any questions regarding class availability.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class availability.
        """
        return self.integration.book_a_class()

    def get_classes(self, num_days: int | None) -> str:
        """Use this function to answer any questions regarding class availability.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class availability.
        """
        if num_days is None:
            return self.integration.get_classes()

        return self.integration.get_classes(num_days)
