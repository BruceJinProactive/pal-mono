from phi.tools.toolkit import Toolkit

from ai.tools.ordering_tools.classes import OrderItem
from ai.tools.ordering_tools.integrations.adora import AdoraIntegration

from . import _utils


class OrderingTools(Toolkit):
    def __str__(self):
        return "OrderingTools"

    def __init__(self, config: dict):
        super().__init__(name="ordering_tools")

        # Toolkit tools (actions)
        self.register(self.add_to_order)
        self.register(self.place_order)
        self.register(self.remove_from_order)

        # Toolkit integrations
        # Map the integration type to the respective class
        # We can refactor to initialize on use if it's a problem
        # TODO: consider an abstract class for each integration?
        self.integration_map = {
            "adora": AdoraIntegration,
            # Add other integrations here
        }

        integration_class = self.integration_map.get(config["type"])

        if not integration_class:
            raise ValueError(f"Unknown integration type: {config['type']}")

        # Lazy load integration
        self.integration = integration_class(**config["settings"])

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
            str: A message indicating the result of adding the item to the order.
        """

        # Create generic order item
        generic_order_item = OrderItem(item_name, size, quantity, modifications)

        # Call integration's add_to_order method
        integrated_order_res = self.integration.add_to_order(generic_order_item)

        return integrated_order_res

    # TODO: Figure out how (if) we want to take in coupons, payment info, delivery type. Hardcode for now.
    def place_order(self, chat_history: list[str]) -> str:
        """
        Places the user's order based on the chat history.

        This function should be used every time the user wants to finish their order, check out, or pay for it.

        Args:
            chat_history (list[str]): The chat history between the user and the assistant. Only include the last 50 messages. If there are less than 50 messages, include all of them.

        Returns:
            str: Result of placing the order, including the total if applicable, and payment instructions if applicable.

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
        cart = _utils.get_cart_info(chat_history)
        if not cart:
            return "There was an issue processing your order. Please try again."

        consumer = _utils.get_consumer_info(chat_history)
        if (
            not consumer
            or consumer.first_name == "N/A"
            or consumer.last_name == "N/A"
            or consumer.phone_number == "N/A"
            or consumer.email == "N/A"
        ):
            return "Ask the user to provide their first name, last name, phone number, and email address to place an order."

        return self.integration.place_order(cart.cart_items, consumer)

    def remove_from_order(self):
        """
        Removes a specified item from the order based on user input.

        Use this function when the user wants to remove an item from their order.

        Args:
            item_name (str): The name of the item to remove.
            size (str): The size of the item to remove.
            modifications (list[str]): Any modifications for the item to remove. Defaults to an empty list.

        Returns:
            str: The result of removing the item from the order.
        """

        # TODO: @brandon - Please implement this function

        return "The item was successfully removed from the order!"
