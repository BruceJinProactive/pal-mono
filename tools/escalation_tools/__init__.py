from ddtrace.llmobs.decorators import tool
from phi.tools.toolkit import Toolkit


class EscalationTools(Toolkit):
    def __str__(self):
        return "EscalationTools"

    def __init__(self, config: dict, **kwargs):
        super().__init__(name="escalation_tools")

        # Toolkit tools (actions)
        self.register(self.get_criteria)
        self.register(self.get_escalated_response)
        self.register(self.get_emergency_response)

        # Toolkit configuration
        self.criteria = config["settings"].get("criteria", None)
        self.escalated_response = config["settings"].get("escalated_response", None)
        self.emergency_response = config["settings"].get("emergency_response", None)

    # ----------------------------------------
    # Toolkit tools (actions)
    # ----------------------------------------

    @tool
    def get_criteria(self) -> str:
        """
        Always call this function first to retrieve the criteria for deciding whether a user prompt needs escalation.

        Returns:
            str: The criteria used to determine if a user prompt should get_escalated_response or get_emergency_response.
        """
        return self.criteria

    @tool
    def get_escalated_response(self) -> str:
        """
        Always call this function to retrieve the escalated response to reply a message.

        Always reply with the response retrieved by this function exactly, do not reword.

        Returns:
            str: The escalated response.
        """
        return self.escalated_response

    @tool
    def get_emergency_response(self) -> str:
        """
        Always call this function to retrieve the emergency response to reply a message.

        Always reply with the response retrieved by this function exactly, do not reword.

        Returns:
            str: The emergency response.
        """
        return self.emergency_response
