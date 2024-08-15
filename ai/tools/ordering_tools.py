from typing import List

from phi.assistant import Assistant
from phi.tools import Toolkit

from ai.tools.adapters.adapters import ServiceAdapters, get_adapter
from ai.tools.adapters.mock_cart import (
    set_delivery_address_to_mock_cart,
    set_order_type_to_mock_cart,
    set_user_info_to_mock_cart,
)
from ai.tools.ordering_classes import OrderItem


class OrderingTools(Toolkit):
    assistant: Assistant = None
    user_id: str = None
    add_cart_to_system_prompt: bool = False

    def __init__(self):
        super().__init__(name="ordering_tools")
        self.register(self.set_user_first_name)
        self.register(self.set_user_last_name)
        self.register(self.set_user_email)
        self.register(self.set_user_phone_number)
        self.register(self.set_order_type)
        self.register(self.set_delivery_street_address)
        self.register(self.set_delivery_suite_number)
        self.register(self.set_delivery_city)
        self.register(self.set_delivery_state)
        self.register(self.set_delivery_zip)
        self.register(self.add_to_order)
        self.register(self.remove_from_order)
        self.register(self.place_order)

    """
    Helper methods for the OrderingTools class.
    """

    def set_fields(
        self, assistant: Assistant, user_id: str, add_cart_to_system_prompt: bool
    ):
        self.assistant = assistant
        self.user_id = user_id
        self.add_cart_to_system_prompt = add_cart_to_system_prompt

        if self.assistant and self.add_cart_to_system_prompt:
            self.set_cart_in_prompt()

    def set_cart_in_prompt(self):
        """
        This function retrieves the items in the user's cart then sets it in the system prompt extra instructions.
        """
        # Get the user's current order
        get_cart_items_adapter = get_adapter(ServiceAdapters.GET_MOCK_CART)
        prompt_addition = get_cart_items_adapter(self.user_id)

        self.assistant.extra_instructions = [prompt_addition]

    """
    Tools for the OrderingTools class.
    """

    def set_user_first_name(self, first_name: str):
        """Call this function when the user provides their first name.
        For example, the user might say
        - My name is John.
        - I'm John.
        - John

        Args:
            first_name (str): The user's first name.

        Returns:
            str: The result of setting the user's first name.
        """

        set_user_info_to_mock_cart(self.user_id, first_name, "", "", "")

        return "First name has been set to " + first_name

    def set_user_last_name(self, last_name: str):
        """Call this function when the user provides their last name.
        For example, the user might say
        - My last name is Smith.
        - I'm Smith.
        - Smith

        Args:
            last_name (str): The user's last name.

        Returns:
            str: The result of setting the user's last name.
        """

        set_user_info_to_mock_cart(self.user_id, "", last_name, "", "")

        return "Last name has been set to " + last_name

    def set_user_email(self, email: str):
        """Call this function when the user provides their email.
        For example, the user might say
        - My email is example@example.com
        - It's example@example.com
        - example@example.com

        Args:
            email (str): The user's email.

        Returns:
            str: The result of setting the user's email.
        """

        set_user_info_to_mock_cart(self.user_id, "", "", email, "")

        return "Email has been set to " + email

    def set_user_phone_number(self, phone_number: str):
        """Call this function when the user provides their phone number.
        For example, the user might say
        - My phone number is (123) 456-7890
        - It's (123) 456-7890
        - (123) 456-7890

        Args:
            phone_number (str): The user's phone number.

        Returns:
            str: The result of setting the user's phone number
        """

        set_user_info_to_mock_cart(self.user_id, "", "", "", phone_number)

        return "Phone number has been set to " + phone_number

    def set_delivery_street_address(self, address: str):
        """Call this function when the user provides their street address aka address line 1 for order delivery.
        If the user mentions the address in their message, this function should be called with the address as the argument.
        For example, the user might say
        - My address is 123 Main St. Apt 1, Austin, TX 78701
        - It's 123 Main St. Apt 1, Austin, TX 78701
        - 123 Main St. Apt 1, Austin, TX 78701
        The street address in these examples is "123 Main St." without "Apt 1". Call set_delivery_suite_number() for the suite number "Apt 1" instead.

        Args:
            address (str): The user's address.

        Returns:
            str: The result of setting the user's address
        """

        return set_delivery_address_to_mock_cart(self.user_id, address, "", "", "", "")

    def set_delivery_suite_number(self, suite_number: str):
        """Call this function when the user provides their suite number for order delivery.
        If the user mentions the suite number in their address, this function should be called with the suite number as the argument.
        For example, the user might say
        - My address is 123 Main St. Apt 1, Austin, TX 78701
        - It's 123 Main St. Apt 1, Austin, TX 78701
        - 123 Main St. Apt 1, Austin, TX 78701
        The suite number in these examples is Apt 1.

        Args:
            suite_number (str): The user's suite number.

        Returns:
            str: The result of setting the user's suite number
        """

        return set_delivery_address_to_mock_cart(
            self.user_id, "", suite_number, "", "", ""
        )

    def set_delivery_city(self, city: str):
        """Call this function when the user provides their city for order delivery.
        If the user mentions the city in their address, this function should be called with the city as the argument.
        For example, the user might say
        - My address is 123 Main St. Apt 1, Austin, TX 78701
        - It's 123 Main St. Apt 1, Austin, TX 78701
        - 123 Main St. Apt 1, Austin, TX 78701
        The city in these examples is Austin.

        Args:
            city (str): The user's city.

        Returns:
            str: The result of setting the user's city
        """

        return set_delivery_address_to_mock_cart(self.user_id, "", "", city, "", "")

    def set_delivery_state(self, state: str):
        """Call this function when the user provides their state for order delivery.
        If the user mentions the state in their address, this function should be called with the state as the argument.
        For example, the user might say
        - My address is 123 Main St. Apt 1, Austin, TX 78701
        - It's 123 Main St. Apt 1, Austin, TX 78701
        - 123 Main St. Apt 1, Austin, TX 78701
        The state in these examples is TX.

        Args:
            state (str): The user's state.

        Returns:
            str: The result of setting the user's state
        """
        return set_delivery_address_to_mock_cart(self.user_id, "", "", "", state, "")

    def set_delivery_zip(self, zip: str):
        """Call this function when the user provides their zip for order delivery.
        If the user mentions the zip code in their address, this function should be called with the zip code as the argument.
        For example, the user might say
        - My address is 123 Main St. Apt 1, Austin, TX 78701
        - It's 123 Main St. Apt 1, Austin, TX 78701
        - 123 Main St. Apt 1, Austin, TX 78701
        The zip code in these examples is 78701.

        Args:
            zip (str): The user's zip.

        Returns:
            str: The result of setting the user's zip
        """

        return set_delivery_address_to_mock_cart(self.user_id, "", "", "", "", zip)

    def set_order_type(self, order_type: str):
        """Call this function when the user provides if they want to pick up their order or have the order delivered to them.
        For example, the user might say
        - deliver my order
        - order a To go
        - order a delivery
        - pickup my order
        - Take out my order
        - Takeout
        - pickup
        - pick up
        - to go
        - delivery
        - I want to pick up my order
        - I want my order delivered
        - I want my order to be delivered to me

        Args:
            order_type (str): Can only be "pickup", or "delivery". "Take out" or "To go" should map to "pickup". "Deliver" or "Delivery" should map to "delivery".

        Returns:
            str: The result of setting order type
        """

        return set_order_type_to_mock_cart(self.user_id, order_type)

    # TODO: Remove the coupling between the ordering tools and the pizza assistant.
    def add_to_order(
        self,
        item_name: str,
        size: str,
        quantity: int = 1,
        modifications: List[str] = [],
    ) -> str:
        """# CONTEXT #
        This function will add one user specified item to the order. You must use this function every time the user expresses interest in ordering.

        #########

        # FUNCTION DESCRIPTION #
        Args:
            item_name (str): The name of the item to add. Do not supply defaults.
            size (str): The size of the item to add. Do not supply defaults.
            quantity (int): The quantity of the item to add.
            modifications (List[str]): Any modifications for the item to add.

        Returns:
            str: The result of adding the item to the order.

        #########

        # EXAMPLES #
        User: I'd like to order 6 chicken wings.
        Tool: add_to_order(item_name=chicken wings, size=6, quantity=1, modifications=[])

        User: Can I have two orders of 12 chicken wings?
        Tool: add_to_order(item_name=chicken wings, size=12, quantity=2, modifications=[])

        User: I'd like a large Big Sur with extra cheese and white sauce.
        Tool: add_to_order(item_name=Big Sur, size=large, quantity=1, modifications=[extra cheese, white sauce])
        """

        order_item = OrderItem(item_name, size, quantity, modifications)
        add_to_order_adapter = get_adapter(ServiceAdapters.ADD_MOCK_CART)
        response = add_to_order_adapter(self.user_id, order_item)

        # Need logic for adding to cart in system prompt.
        # Current: Remove then add again.
        if self.add_cart_to_system_prompt:
            self.set_cart_in_prompt()

        return response

    def remove_from_order(
        self, item_name: str, size: str, quantity: int, modifications: List[str] = []
    ):
        """Use this function when the user wants to remove an item from their order.
        For example, the user might say
        - Remove a large big sur.
        - I'd like to remove a medium big sur.
        - I want to remove a small Pesto.
        - Take out a large Pepperoni.
        - Remove a large big sur with extra cheese and no onions.
        - I'd like to remove a medium big sur with extra cheese and no onions.
        - I want to remove a small Pesto with extra cheese and no onions.

        Args:
            item_name (str): The name of the item to remove.
            size (str): The size of the item to remove.
            quantity (int): The quantity of the item to remove.
            modifications (List[str]): Any modifications for the item to remove.

        Returns:
            str: The result of removing the item from the order.
        """

        order_item = OrderItem(item_name, size, quantity, modifications)
        remove_from_order_adapter = get_adapter(ServiceAdapters.REMOVE_MOCK_CART)
        remove_from_order_adapter(self.user_id, order_item)

        # Need logic for adding to cart in system prompt.
        # Current: Remove then add again.
        if self.add_cart_to_system_prompt:
            self.set_cart_in_prompt()

        return "The item was successfully removed from the order!"

    # TODO: Figure out how (if) we want to take in coupons, payment info, delivery type. Hardcode for now.
    def place_order(self):
        """Use this function when the user wants to finish their order or check out or pay for it.
        For example, the user might say
        - Place my order.
        - Check out.
        - Pay for my order.
        - I'm ready to place my order.
        - I'm ready to check out.
        - I'm ready to pay for my order.

        Returns:
            str: Result of placing order, the total if applicable, and where to pay if applicable.
        """

        # Can place some wrapper logic here.

        place_order_adapter = get_adapter(ServiceAdapters.CHECKOUT_MOCK_CART)

        # Ex. can clear cart after ordering + error handling.

        return place_order_adapter(self.user_id)

    # PLACEHOLDER FUNCTION
    def get_order_details(self):
        return None

    # PLACEHOLDER FUNCTION
    def restart_order(self):
        return None
