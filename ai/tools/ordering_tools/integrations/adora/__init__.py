import json

from openai import OpenAI

from ai.tools.ordering_tools.classes import Consumer, LLMOrderItem, OrderItem

from . import _apis, _utils
from .classes import AdoraOrderItem


class AdoraIntegration:
    def __init__(
        self, api_key: str, api_secret: str, openai_api_key: str, openai_model: str
    ):
        self.store_id = "9WHCV"
        self.api_key = api_key
        self.api_secret = api_secret
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.openai_model = openai_model

    def add_to_order(self, order_item: OrderItem):
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

        if not validated_order:
            return "Failed to validate order."


        return f"Added {order_item.item_name} to your cart."

    def place_order(self, cart: list[LLMOrderItem], consumer: Consumer) -> str:
        menu = {}  # TODO Should be referenced from the knowledge base in SQL
        with open("data/pizza/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
            menu = json.load(read_f)

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        order_items = []

        for order_item in cart:
            convert_item_success, adora_order_item = _utils.validate_and_convert_item(
                order_item, menu, self.openai_client, self.openai_model
            )

            if not convert_item_success:
                return adora_order_item  # this is an error string

            order_items.append(adora_order_item)

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_id, order_items, consumer
        )

        if not validated_order:
            return "Failed to validate order."

        # save validated order to Adora system and get the order ID back
        saved_order = _apis.save_validate_order(bearer_token, validated_order.Key)

        # place order
        if _apis.place_order(
            bearer_token, saved_order.OrderID, self.store_id, consumer.phone_number
        ):
            return "Order placed successfully."
        else:
            return "There was an issue placing the order. Please try again."
