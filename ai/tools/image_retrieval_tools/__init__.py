import inspect

from phi.tools.toolkit import Toolkit

from .integrations.pinecone import PineconeIntegration


class ImageRetrievalTools(Toolkit):
    def __str__(self):
        return "ImageRetrievalTools"

    def __init__(self, config: dict, **kwargs):
        super().__init__(name="image_retrieval_tools")

        # Load user_id
        self.user_id = kwargs["user_id"]

        # Toolkit tools (actions)
        self.register(self.retrieve_image_by_chat_history)

        # Toolkit integrations
        # TODO: create a tool integration module
        self.integration_map = {
            "pinecone": PineconeIntegration,
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

    def retrieve_image_by_chat_history(self, chat_history: list[str]) -> str:
        """Retrieves an image from a vector database based on the user's chat history.

        This function is called when the user asks to see an image of a product or when the user asks for a recommendation.

        Args:
            chat_history (list[str]): The chat history between the user and the agent. Only include the last 50 messages. If there are less than 50 messages, include all of them.

        Returns:
            str: A string representing the image urls.

        """

        return self.integration.retrieve_image_by_chat_history(chat_history)
