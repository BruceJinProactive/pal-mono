from phi.tools.toolkit import Toolkit


class EscalationTools(Toolkit):
    def __str__(self):
        return "EscalationTools"

    def __init__(self, config: dict, **kwargs):
        super().__init__(name="escalation_tools")

        # Toolkit tools (actions)
        self.register(self.get_criteria)
        self.register(self.get_response)

        # Toolkit configuration
        self.criteria = config["settings"].get("criteria", None)
        self.response = config["settings"].get("response", None)

    # ----------------------------------------
    # Toolkit tools (actions)
    # ----------------------------------------

    def get_criteria(self) -> str:
        """
        Always call this function first to retrieve the criteria for deciding whether a user prompt needs escalation.

        Returns:
            str: The criteria used to determine if a user prompt should be escalated.
        """
        return self.criteria

    def get_response(self) -> str:
        """
        Always call this function first to retrieve the response to reply to user when a user prompt needs to be escalated.

        Always reply with the response retrieved by this function exactly when a user prompt needs to be escalated, do not reword.

        Returns:
            str: The escalation response.
        """
        return self.response
