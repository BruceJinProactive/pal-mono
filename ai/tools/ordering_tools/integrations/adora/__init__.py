import json

from openai import OpenAI

from ai.tools.ordering_tools.classes import OrderItem

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

        # Invalid quantity
        if order_item.quantity < 1:
            return "Quantity must be at least 1."
        if order_item.quantity > 100:
            return "Quantity must be at most 100."

        # Get Adora-specific item id and size id
        adora_item_id_res = _utils.get_adora_item_id(
            menu, order_item.item_name, self.openai_client, self.openai_model
        )
        if not adora_item_id_res.success:
            return adora_item_id_res.message

        adora_size_id_res = _utils.get_adora_size_id(
            menu,
            int(adora_item_id_res.message),
            order_item.size,
            self.openai_client,
            self.openai_model,
        )
        if not adora_size_id_res.success:
            return adora_size_id_res.message

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        # TODO modifications
        # adora_modifications_res = get_adora_modifications(
        #     int(adora_item_id_res.message),
        #     order_item.modifications,
        # )

        # transform generic order item into Adora order item
        adora_order_item = AdoraOrderItem(
            int(adora_item_id_res.message),
            int(adora_size_id_res.message),
            order_item.quantity,
            "",
            0,
            order_item.modifications,
        )

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_id, adora_order_item
        )

        if not validated_order:
            return "Failed to validate order."

        # save validated order to Adora system and get the order ID back
        saved_order = _apis.save_validate_order(bearer_token, validated_order.Key)

        return f"Added {order_item.item_name} to your cart. You absolutely must include the order number {saved_order.OrderID}."

    def place_order(self, order_id: int):
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        # place order
        return _apis.place_order(bearer_token, order_id, self.store_id)
