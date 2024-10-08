from typing import Optional

from phi.tools.toolkit import Toolkit

from ai.tools.escalation_tools.integrations.mindzero import MindZeroIntegration


class EscalationTools(Toolkit):
    def __str__(self):
        return "EscalationTools"

    def __init__(self, config: dict):
        super().__init__(name="escalation_tools")

        # Toolkit tools (actions)
        self.register(self.get_criteria)
        self.register(self.get_response)

        # Toolkit configuration
        # self.api_key = config.get("api_key", None)
        # self.api_secret = config.get("api_secret", None)

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

    def get_criteria(self) -> str:
        """
        Always call this function first to retrieve the criteria for deciding whether a user prompt needs escalation.

        Returns:
            str: The criteria used to determine if a user prompt should be escalated.
        """
        return self.integration.get_criteria()

    def get_response(self) -> str:
        """
        Always call this function first to retrieve the response to reply to user when a user prompt needs to be escalated.

        Always reply with the response retrieved by this function exactly when a user prompt needs to be escalated, do not reword.

        Returns:
            str: The escalation response.
        """
        return self.integration.get_response()
