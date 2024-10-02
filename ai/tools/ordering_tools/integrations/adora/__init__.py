import json
from os import getenv

from openai import OpenAI

from ai.llm import _settings
from ai.tools.ordering_tools.classes import Consumer, LLMOrderItem, OrderItem
from ai.tools.ordering_tools.integrations.adora.classes import OrderCalculationResult

from . import _apis, _utils


class AdoraIntegration:
    def __init__(self, api_key: str, api_secret: str):
        self.store_id = "9WHCV"
        self.api_key = api_key
        self.api_secret = api_secret
        self.openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
        self.openai_model = _settings.ai_settings.gpt_4o_2024_08_06

    def add_to_order(self, order_item: OrderItem) -> str:
        menu = {}  # TODO Should be referenced from the knowledge base in SQL
        with open("data/pizza/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
            menu = json.load(read_f)

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        convert_item_success, adora_order_item = _utils.validate_and_convert_item(
            order_item, menu, self.openai_client, self.openai_model
        )
        if not convert_item_success:
            return adora_order_item  # this is an error string

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_id, [adora_order_item]
        )

        if isinstance(validated_order, OrderCalculationResult):
            return f"Added {order_item.item_name} for {validated_order.SubTotal} to your cart."
        else:
            return "Failed to validate order."

    def place_order(self, cart: list[LLMOrderItem], consumer: Consumer) -> str:
        menu = {}  # TODO Should be referenced from the knowledge base in SQL
        with open("data/pizza/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
            menu = json.load(read_f)

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        order_items = []
        order_summary = []  # List to hold the summary of items and their prices

        for order_item in cart:
            convert_item_success, adora_order_item = _utils.validate_and_convert_item(
                order_item, menu, self.openai_client, self.openai_model
            )

            if not convert_item_success:
                return adora_order_item  # this is an error string

            order_items.append(adora_order_item)
            # Append item details to order_summary for later display
            order_summary.append(f"{order_item.item_name}")

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_id, order_items, consumer
        )
        if not validated_order:
            return "Failed to validate order."

        # save validated order to Adora system and get the order ID back
        saved_order = _apis.save_validate_order(bearer_token, validated_order.Key)

        # place order
        if saved_order and _apis.place_order(
            bearer_token, saved_order.OrderID, self.store_id, consumer.phone_number
        ):
            # Combine the summary of items with the total price
            return (
                "Order placed successfully!\n"
                "Here are the details of your order, list the item name:\n"
                f"{order_summary}\n"
                f"Subtotal: ${validated_order.SubTotal}"
                f"Total with Tax: ${validated_order.Total}"
            )
        else:
            return "There was an issue placing the order. Please try again."
