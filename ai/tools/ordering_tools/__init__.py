import inspect

from phi.tools.toolkit import Toolkit

from ai.tools.ordering_tools.classes import OrderItem
from ai.tools.ordering_tools.integrations.adora import AdoraIntegration
from utils.log import logger


class OrderingTools(Toolkit):
    def __str__(self):
        return "OrderingTools"

    def __init__(self, config: dict, user_id: str):
        super().__init__(name="ordering_tools")

        # Load user_id
        self.user_id = user_id

        # Toolkit tools (actions)
        self.register(self.add_to_order)
        self.register(self.list_coupons)
        self.register(self.place_order)
        self.register(self.remove_from_order)

        # Toolkit integrations
        # Map the integration type to the respective class
        self.integration_map = {
            "adora": AdoraIntegration,
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

        # Custom system prompts
        self.cart_conversion_sys_prompt = config.get("cart_conversion_sys_prompt", "")
        if isinstance(self.cart_conversion_sys_prompt, list):
            self.cart_conversion_sys_prompt = " ".join(self.cart_conversion_sys_prompt)
        elif type(self.cart_conversion_sys_prompt) is not str:
            self.cart_conversion_sys_prompt = ""

    # ----------------------------------------
    # Toolkit tools (actions)
    # ----------------------------------------

    def add_to_order(
        self,
        item_name: str,
        size: str,
        quantity: int = 1,
        modifications: list[str] = [],
    ) -> str:
        """
        Adds a specified item to the order based on user input.

        This function will add one user-specified item to the order when the user expresses interest in ordering and provides the item name, size, quantity, and any modifications.

        Args:
            item_name (str): The name of the item to add.
            size (str): The size of the item to add.
            quantity (int): The quantity of the item to add. Defaults to 1.
            modifications (list[str]): Any modifications for the item to add. Defaults to an empty list.

        Returns:
            str: A message including quanity, size, item_name, with modifications for the price or a failure to add item message.
        """
        logger.debug(
            f"[OrderingTools.add_to_order] Item: {item_name}, Size: {size}, Quantity: {quantity}, Modifications: {modifications}"
        )
        # Create generic order item
        generic_order_item = OrderItem(item_name, size, quantity, modifications)

        # Call integration's add_to_order method
        return self.integration.add_to_order(generic_order_item)

    def list_coupons(self):
        """
        Lists all available coupons. Do NOT use an ordered list with numbers when listing the coupons.

        Use this function when the user wants to see all available coupons.

        Returns:
            str: A message listing all available coupons.
        """

        return self.integration.list_coupons()

    def place_order(self, chat_history: list[str]) -> str:
        """
        This function should be called every time the user requests to place order, checkout, or pay.

        Places the user's order based on the chat history (both user messages and agent messages).

        The user must provide the fulfillment strategy (delivery or pickup), and the delivery address if the fulfillment strategy is delivery.

        You must provide the user with the ordered item, price, and order id in the response.

        Args:
            chat_history (list[str]): Chat history between user and agent. Be sure to include both user messages and agent responses.

        Returns:
            str: Result of placing the order, including the total and order id if applicable, and payment instructions if applicable.

        Examples:
            User: Place my order
            Tool: place_order()

            User: checkout
            Tool: place_order()

            User: that'll be all
            Tool: place_order()

            User: I'm ready to pay
            Tool: place_order()

            User: just those items please
            Tool: place_order()
        """
        logger.debug(f"[OrderingTools.place_order] Chat history: {chat_history}")

        return self.integration.place_order(chat_history, self.user_id)

    def remove_from_order(
        self,
        item_name: str,
        size: str,
        quantity: int = 1,
        modifications: list[str] = [],
    ) -> str:
        """
        Removes a specified item from the order based on user input.

        Use this function when the user wants to remove an item from their order.

        Args:
            item_name (str): The name of the item to remove.
            size (str): The size of the item to remove.
            quantity (int): The quantity of the item to remove. Defaults to 1.
            modifications (list[str]): Any modifications for the item to remove. Defaults to an empty list.

        Returns:
            str: The result of removing the item from the order.
        """
        logger.debug(
            f"[OrderingTools.remove_from_order] Removing item from order: {item_name}, Size: {size}, Quantity: {quantity}, Modifications: {modifications}"
        )

        return self.integration.remove_from_order()
