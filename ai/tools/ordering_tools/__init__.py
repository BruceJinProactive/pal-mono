from os import getenv

from phi.tools import Toolkit

from ai.llm import _settings
from ai.tools.ordering_tools.integrations.adora import AdoraIntegration
from ai.tools.ordering_tools.ordering_classes import OrderItem

from . import _utils


class OrderingTools(Toolkit):
    def __str__(self):
        return "OrderingTools"

    def __init__(self, config: dict):
        super().__init__(name="ordering_tools")
        self.register(self.add_to_order)
        self.register(self.remove_from_order)
        self.register(self.place_order)

        self.api_key = config["api_key"]
        self.api_secret = config["api_secret"]
        self.openai_api_key = getenv("OPENAI_API_KEY")
        self.openai_model = _settings.ai_settings.gpt_4o_2024_08_06
        if (
            not self.api_key
            or not self.api_secret
            or not self.openai_api_key
            or not self.openai_model
        ):
            raise ValueError(
                "Please reach out to our support team at help@proactiveailab.com for assistance. Message: API key and secret are required for ordering tools."
            )

        # Map the integration type to the respective class
        # We can refactor to initialize on use if it's a problem
        # TODO: consider an abstract class for each integration?
        self.integration_map = {
            "adora": AdoraIntegration(
                self.api_key,
                self.api_secret,
                self.openai_api_key,
                self.openai_model,
            ),
        }
        self.integration = self.integration_map[config["type"]]

    """
    Helper methods for the OrderingTools class.
    """

    def add_to_order(
        self,
        item_name: str,
        size: str,
        quantity: int = 1,
        modifications: list[str] = [],
    ) -> str:
        """# CONTEXT #
        This function will add one user specified item to the order, only when the user expresses interest in ordering and the size, name, quantity, and modifications are indicated.

        #########

        # FUNCTION DESCRIPTION #
        Args:
            item_name (str): The name of the item to add. Do not supply defaults.
            size (str): The size of the item to add. Do not supply defaults.
            quantity (int): The quantity of the item to add.
            modifications (list[str]): Any modifications for the item to add.

        Returns:
            str: The result of adding the item to the order.

        #########

        # EXAMPLES #
        User: I'd take a large Big Sur.
        Tool: add_to_order(item_name=Big Sur, size=large, quantity=1, modifications=[])
        """

        # Create generic order item
        generic_order_item = OrderItem(item_name, size, quantity, modifications)

        # Call integration's add_to_order method
        integrated_order_res = self.integration.add_to_order(generic_order_item)

        return integrated_order_res

    def remove_from_order(self):
        """Use this function when the user wants to remove an item from their order.
        For example, the user might say
        - Remove a large big sur.
        - I'd like to remove a medium big sur.
        - I want to remove a small Pesto.
        - Take out a large Pepperoni.
        - Remove a large big sur with extra cheese and no onions.
        - I'd like to remove a medium big sur with extra cheese and no onions.
        - I want to remove a small Pesto with extra cheese and no onions.
        - I want to clear my cart.

        Returns:
            str: The result of removing the item from the order.
        """

        return "The item was successfully removed from the order!"

    # TODO: Figure out how (if) we want to take in coupons, payment info, delivery type. Hardcode for now.
    def place_order(self, chat_history: list[str]) -> str:
        """# CONTEXT #
        This function will place the user's order. You must use this function every time the user wants to finish their order or check out or pay for it.

        # FUNCTION DESCRIPTION #
        Args:
            chat_history (list[str]): The chat history between the user and the assistant. Only include the last 50 messages.

        Returns:
            str: Result of placing order, the total if applicable, and where to pay if applicable.

        # EXAMPLES #
        User: Place my order
        Tool: place_order()

        User: checkout
        Tool: place_order()

        User: that'll be all
        Tool: place_order()

        User: im ready to pay
        Tool: place_order()

        User: just those items please
        Tool: place_order()
        """

        cart = _utils.get_cart_info(chat_history)
        if not cart:
            return "There was an issue processing your order. Please try again."

        # Call integration's add_to_order method to validate order
        integrated_order_res = self.integration.add_to_order(cart.cart_items[0])

        # Given validated order message string, extract order ID
        saved_adora_order = _utils.get_order_id(integrated_order_res)
        if not saved_adora_order:
            return "There was an issue processing your order. Please try again."
        order_id = saved_adora_order.order_id

        success = self.integration.place_order(order_id)

        if success:
            return "The order has been placed."
        else:
            return "There was an issue placing the order. Please try again."
