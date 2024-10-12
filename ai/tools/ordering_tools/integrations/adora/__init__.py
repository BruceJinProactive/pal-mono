import json
from os import getenv
from typing import Any

from geopy.geocoders import Nominatim
from openai import OpenAI

from ai.knowledge import get_knowledge
from ai.llm import _settings
from ai.tools.ordering_tools.classes import (
    Consumer,
    FulfillmentStrategy,
    GenericDeliveryAddress,
    LLMOrderItem,
    OrderItem,
)
from ai.tools.ordering_tools.integrations.adora.classes import (
    AdoraDeliveryAddress,
    AdoraOrderCalculationResult,
    AdoraOrderItem,
    AdoraOrderType,
)

from . import _apis, _utils


class AdoraIntegration:
    def __init__(
        self,
        account_name: str,
        api_key: str,
        api_secret: str,
        menu_name: str,
        store_id: str,
    ):
        self.account_name = account_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.menu_name = menu_name
        self.store_id = store_id
        self.openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
        self.openai_model = _settings.ai_settings.gpt_4o_2024_08_06

    def add_to_order(self, order_item: OrderItem) -> str:
        # Get menu from knowledge base based on menu name
        menu = self.get_adora_menu()

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        convert_item_success, adora_order_item = _utils.validate_and_convert_item(
            order_item, menu, self.openai_client, self.openai_model
        )
        if not convert_item_success and isinstance(adora_order_item, str):
            return adora_order_item  # this is an error string

        if not isinstance(adora_order_item, AdoraOrderItem):
            return "Failed to convert order item."

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_id, [adora_order_item], 0
        )

        if isinstance(validated_order, AdoraOrderCalculationResult):
            return f"Added {order_item.item_name} for {validated_order.SubTotal} to your cart."
        else:
            return "Failed to validate order."

    def list_coupons(self):
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        coupons = _apis.list_coupons(bearer_token, self.store_id)

        if coupons and len(coupons) > 0:
            return (
                "When listing coupons, do NOT use an ordered list."
                + "Here are the available coupons: "
                + "\n\n".join([f"{c.name}\n{c.description}" for c in coupons])
            )
        else:
            return "There are no available coupons at this time."

    def place_order(
        self,
        cart: list[LLMOrderItem],
        consumer: Consumer,
        fulfillment_strategy: FulfillmentStrategy,
        delivery_address: GenericDeliveryAddress | None,
        generic_coupon: str,
    ) -> str:
        # Get menu from knowledge base based on menu name
        menu = self.get_adora_menu()

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        order_items = []
        order_summary = []  # List to hold the summary of items and their prices

        for order_item in cart:
            order_item = OrderItem(
                order_item.item_name,
                order_item.size,
                order_item.quantity,
                order_item.modifications,
            )
            convert_item_success, adora_order_item = _utils.validate_and_convert_item(
                order_item, menu, self.openai_client, self.openai_model
            )

            if not convert_item_success and isinstance(adora_order_item, str):
                return adora_order_item  # this is an error string

            if not isinstance(adora_order_item, AdoraOrderItem):
                return "Failed to convert order item."

            order_items.append(adora_order_item)
            # Append item details to order_summary for later display
            order_summary.append(f"{order_item.item_name}")

        # convert generic coupon to Adora coupon
        if generic_coupon == "N/A":
            adora_coupon_id = 0
        else:
            possible_coupons = _apis.list_coupons(bearer_token, self.store_id)
            adora_coupon = _utils.convert_coupon(
                possible_coupons, generic_coupon, self.openai_client, self.openai_model
            )
            adora_coupon_id = adora_coupon.id if adora_coupon else 0

        # convert generic fulfillment strategy to Adora order type
        if (
            fulfillment_strategy == FulfillmentStrategy.DINEIN
            or fulfillment_strategy == FulfillmentStrategy.NA
        ):
            return "Dine-in is not supported by Adora POS. Please choose delivery or pickup."
        fulfillment_conversion_map = {
            FulfillmentStrategy.DELIVERY: AdoraOrderType.Delivery,
            FulfillmentStrategy.PICKUP: AdoraOrderType.TakeOut,
        }
        order_type = fulfillment_conversion_map[fulfillment_strategy]

        # validate address if delivery order
        adora_delivery_address = None
        if order_type == AdoraOrderType.Delivery:
            if not delivery_address:
                return "Ask the user to provide a delivery address to place a delivery order."

            # convert address to lat long coordinates
            # TODO: Usage limited to 1qps without API key. Upgrade to paid plan when needed.
            # TODO: https://aws.amazon.com/location/
            geolocator = Nominatim(user_agent="pal")
            geocoded_loc = geolocator.geocode(
                {
                    "street": delivery_address.address,
                    "city": delivery_address.city,
                    "state": delivery_address.state,
                    "country": "USA",
                    "postalcode": delivery_address.zip_code,
                }
            )
            if not geocoded_loc:
                return "The address that the user provided is invalid. Please provide a valid address."

            # call Adora address validation API
            validated_address_success, validated_address = _apis.validate_address(
                bearer_token,
                self.store_id,
                str(geocoded_loc.latitude),
                str(geocoded_loc.longitude),
            )
            if not validated_address_success or isinstance(validated_address, str):
                if isinstance(validated_address, str):
                    return validated_address  # this is an error string
                return "Address is invalid. Tell the user to provide a valid address."

            adora_delivery_address = AdoraDeliveryAddress(
                address=delivery_address.address,
                city=delivery_address.city,
                state=delivery_address.state,
                zip=delivery_address.zip_code,
                # set the lat long from the geocoded location
                lat=geocoded_loc.latitude,
                lng=geocoded_loc.longitude,
                # set the typeId from the validated address
                # TODO why does Adora return an array of addresses?
                typeId=validated_address[0].typeId,
            )

        # validate order
        validated_order = _apis.validate_order(
            bearer_token,
            self.store_id,
            order_items,
            adora_coupon_id,
            order_type,
            consumer,
            adora_delivery_address,
        )
        if not validated_order:
            return "Failed to validate order."

        # save validated order to Adora system and get the order ID back
        saved_order = _apis.save_validate_order(bearer_token, validated_order.Key)

        # TODO race condition here, need to add while loop to retry if order is not found in place_order

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

    def get_adora_menu(self) -> Any:
        menu = {}  # TODO Temporary fix, investigating knowledge SQL performance
        with open("data/pizza/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
            menu = json.load(read_f)
        return menu
