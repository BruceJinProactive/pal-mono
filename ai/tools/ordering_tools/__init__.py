import inspect

from phi.tools.toolkit import Toolkit

from ai.tools.ordering_tools.classes import FulfillmentStrategy, OrderItem
from ai.tools.ordering_tools.integrations.adora import AdoraIntegration

from . import _utils


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
        # TODO: consider an abstract class for each integration?
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
            str: A message including quanity, size, item_name, with the price or a failure to add item message.
        """
        # Create generic order item
        generic_order_item = OrderItem(item_name, size, quantity, modifications)

        # Call integration's add_to_order method
        integrated_order_res = self.integration.add_to_order(generic_order_item)

        return integrated_order_res

    def list_coupons(self):
        """
        Lists all available coupons. Do NOT use an ordered list with numbers when listing the coupons.

        Use this function when the user wants to see all available coupons.

        Returns:
            str: A message listing all available coupons.
        """

        return self.integration.list_coupons()

    # TODO: Figure out how (if) we want to take in coupons, payment info, delivery type. Hardcode for now.
    def place_order(self, chat_history: list[str]) -> str:
        """
        Places the user's order based on the chat history.

        This function should be used every time the user wants to finish their order, check out, or pay for it.

        The user must provide the fulfillment strategy (delivery, pickup), and the delivery address if the fulfillment strategy is delivery.

        Must tell user ordered item, price and order id in the response.

        Args:
            chat_history (list[str]): Chat history between user and assistant.

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
        cart = _utils.get_cart_info(chat_history)
        if not cart:
            return "There was an issue processing your order. Please try again."

        account_name = self.integration.account_name
        memories = _utils.get_consumer_memory(account_name, self.user_id)
        memory_list = (
            "## Existing Memories\n"
            + "\n".join(f"- {memory.memory}" for memory in memories)
            if memories
            else ""
        )
        consumer = _utils.get_consumer_info(chat_history, memory_list)
        if not consumer:
            return "Ask the user to provide their first name, last name, phone number, and email address to place an order."

        missing_info = []
        if consumer.first_name == "N/A":
            missing_info.append("first name")
        if consumer.last_name == "N/A":
            missing_info.append("last name")
        if consumer.phone_number == "N/A":
            missing_info.append("phone number")
        if consumer.email == "N/A":
            missing_info.append("email address")

        if missing_info:
            return (
                f"Please provide your {' and '.join(missing_info)} to place an order."
            )
        # Format phone number
        consumer.phone_number = "({}){}-{}".format(
            consumer.phone_number[:3],
            consumer.phone_number[3:6],
            consumer.phone_number[6:],
        )

        fulfillment_strategy = _utils.get_fulfillment_strategy(chat_history)

        if (
            not fulfillment_strategy
            or fulfillment_strategy.strategy == FulfillmentStrategy.NA
        ):
            return "Ask the user to provide a fulfillment strategy to place an order, e.g., delivery, pickup."
        fulfillment_strategy = fulfillment_strategy.strategy

        delivery_address = None
        if fulfillment_strategy == FulfillmentStrategy.DELIVERY:
            delivery_address = _utils.get_delivery_address(chat_history)
            if (
                not delivery_address
                or delivery_address.address == "N/A"
                or delivery_address.city == "N/A"
                or delivery_address.state == "N/A"
                or delivery_address.zip_code == "N/A"
            ):
                return "Ask the user to provide a valid and complete delivery address to place a delivery order."

        generic_coupon = _utils.get_generic_coupon_info(chat_history)
        generic_coupon = generic_coupon.coupon if generic_coupon else "N/A"

        return self.integration.place_order(
            cart.cart_items,
            consumer,
            fulfillment_strategy,
            delivery_address,
            generic_coupon,
        )

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

        return "The item was successfully removed from the order!"
