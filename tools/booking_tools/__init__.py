import inspect

from phi.tools.toolkit import Toolkit

from tools.booking_tools.integrations.mindzero import MindZeroIntegration


class BookingTools(Toolkit):
    def __str__(self):
        return "BookingTools"

    def __init__(self, config: dict, **kwargs):
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

        # Get the list of valid parameters for the integration_class constructor
        valid_params = inspect.signature(integration_class).parameters

        # Filter the config["settings"] dictionary to include only valid parameters
        filtered_settings = {
            parameter: value
            for parameter, value in config["settings"].items()
            if parameter in valid_params
        }

        #  Only the valid parameters needed by integration_class are passed during initialization
        self.integration = integration_class(**filtered_settings)

    # ----------------------------------------
    # Toolkit tools (actions)
    # ----------------------------------------

    # NOTE: will add chat history when a new integration is added
    def book_a_class(self) -> str:
        """
        Use this function to book a class.

        Args:
            num_days (int): Number of days in advance to look for.

        Returns:
            str: JSON string of class availability.
        """
        return self.integration.book_a_class()

    def get_classes(self, num_days: int = 7) -> str:
        """
        Use this function to answer any questions regarding class availability.


        Args:
            num_days (int): Number of days in advance to look for. Defaults to 7 if user doesn't supply.

        Returns:
            str: JSON string of class availability or a class scheduler status update.
        """
        return self.integration.get_classes(num_days)
