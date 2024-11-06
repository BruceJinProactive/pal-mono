from os import getenv
from typing import Any, Literal

from geopy.geocoders import Nominatim
from openai import OpenAI

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
from utils.log import logger

from . import _apis, _utils


class AdoraIntegration:
    def __init__(
        self,
        account_name: str,
        api_key: str,
        api_secret: str,
        store_id: str,
        adora_conversion_examples: dict[
            Literal["items", "sizes", "modifiers", "coupons"], dict[str, str]
        ] = {},
    ):
        self.account_name = account_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.store_id = store_id
        self.adora_conversion_examples = adora_conversion_examples
        self.openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
        self.openai_model = _settings.ai_settings.gpt_4o_2024_08_06

    def add_to_order(self, order_item: OrderItem) -> str:
        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        # Get menu from knowledge base based on menu name
        menu = _apis.get_adora_menu(self.store_id, bearer_token)
        if not menu:
            return "Failed to get menu, please try again."
        menu_maps = _utils.get_menu_maps(menu)
        size_map = _utils.get_size_description_map(menu)

        convert_item_success, adora_order_item = _utils.validate_and_convert_item(
            order_item,
            menu_maps,
            size_map,
            menu["modifiers"],
            menu["modifier_groups"],
            self.adora_conversion_examples.get("items", {}),
            self.adora_conversion_examples.get("sizes", {}),
            self.adora_conversion_examples.get("modifiers", {}),
            self.openai_client,
            self.openai_model,
        )
        if not convert_item_success and isinstance(adora_order_item, str):
            return adora_order_item  # this is an error string

        if not isinstance(adora_order_item, AdoraOrderItem):
            return "Failed to convert order item."

        # TODO add coupon to order validation here in add_to_order too

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_id, [adora_order_item], 0
        )

        if isinstance(validated_order, AdoraOrderCalculationResult):
            return f"In the response, include quantity: {adora_order_item.quantity}, size: {adora_order_item.size}, item_name: {adora_order_item.item_name}, with modifications: {adora_order_item.modifications} for price: {validated_order.SubTotal} to your cart."
        else:
            return "Failed to validate order."

    def list_coupons(self):
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        coupons = _apis.list_coupons(bearer_token, self.store_id)

        if coupons and len(coupons) > 0:
            return (
                "List the available coupons below. When listing coupons, do NOT use an ordered list. "
                + "Also, inform the user that to apply a coupon, they must explicitly mention the coupon name during checkout.\n"
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
        logger.debug("[AdoraIntegration.place_order] Placing order...")
        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        # Get menu from knowledge base based on menu name
        menu = _apis.get_adora_menu(self.store_id, bearer_token)
        if not menu:
            return "Failed to get menu, please try again."

        menu_maps = _utils.get_menu_maps(menu)
        size_map = _utils.get_size_description_map(menu)

        order_items = []
        order_summary = []  # List to hold the summary of items and their prices

        logger.debug(
            "[AdoraIntegration.place_order] Converting items to Adora order items..."
        )

        for order_item in cart:
            order_item = OrderItem(
                order_item.item_name,
                order_item.size,
                order_item.quantity,
                order_item.modifications,
            )
            convert_item_success, adora_order_item = _utils.validate_and_convert_item(
                order_item,
                menu_maps,
                size_map,
                menu["modifiers"],
                menu["modifier_groups"],
                self.adora_conversion_examples.get("items", {}),
                self.adora_conversion_examples.get("sizes", {}),
                self.adora_conversion_examples.get("modifiers", {}),
                self.openai_client,
                self.openai_model,
            )

            if not convert_item_success and isinstance(adora_order_item, str):
                logger.debug(
                    f"[AdoraIntegration.place_order] Failed to convert item {order_item}: {adora_order_item}"
                )
                return adora_order_item  # this is an error string

            if not isinstance(adora_order_item, AdoraOrderItem):
                return "Failed to convert order item."

            order_items.append(adora_order_item)
            logger.debug(
                f"[AdoraIntegration.place_order] Successfully converted item: {order_item.item_name}"
            )
            # Append item details to order_summary for later display
            order_summary.append(
                f"{order_item.item_name if order_item.quantity == 1 else f'{order_item.quantity}x {order_item.item_name}'}"
            )

        logger.debug(
            "[AdoraIntegration.place_order] Converted items to Adora order items."
        )

        # convert generic coupon to Adora coupon
        if generic_coupon == "N/A":
            adora_coupon_id = 0
        else:
            logger.debug(
                "[AdoraIntegration.place_order] Converting generic coupon to Adora coupon..."
            )
            possible_coupons = _apis.list_coupons(bearer_token, self.store_id)
            adora_coupon_res = _utils.convert_coupon(
                possible_coupons,
                generic_coupon,
                self.openai_client,
                self.openai_model,
                self.adora_conversion_examples.get("coupons", {}),
            )
            if not adora_coupon_res.success:
                logger.warning(
                    f"[AdoraIntegration.place_order] Failed to convert coupon: {adora_coupon_res.message}"
                )
                return adora_coupon_res.message
            adora_coupon_id = int(adora_coupon_res.message)
            logger.debug(
                f"[AdoraIntegration.place_order] Coupon conversion result: {adora_coupon_id if adora_coupon_id else 'No coupon applied'}"
            )

        # convert generic fulfillment strategy to Adora order type
        if fulfillment_strategy == FulfillmentStrategy.NA:
            return "Ask the user to provide a fulfillment strategy to place an order, e.g., delivery, pickup."
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
            geo_payload = {
                "street": delivery_address.address,
                "city": delivery_address.city,
                "state": delivery_address.state,
                "country": "USA",
                "postalcode": delivery_address.zip_code,
            }
            logger.debug(
                "[AdoraIntegration.place_order] Geolocator payload: " + str(geo_payload)
            )
            geocoded_loc: Any = geolocator.geocode(geo_payload)
            if not geocoded_loc:
                return "The address that the user provided is invalid. Please provide a valid address."

            logger.debug(
                "[AdoraIntegration.place_order] Nominatim API result: "
                + str(geocoded_loc.latitude)
                + ", "
                + str(geocoded_loc.longitude)
            )

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
        logger.debug("[AdoraIntegration.place_order] Validating order...")
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
        logger.debug("[AdoraIntegration.place_order] Saving validated order...")
        saved_order = _apis.save_validate_order(bearer_token, validated_order.Key)

        # place order
        if saved_order and _apis.place_order(
            bearer_token, saved_order.OrderID, self.store_id, consumer.phone_number
        ):
            successful_order_response = (
                "Order placed successfully!\n"
                "Here are the details of your order, list the item name:\n"
                f"{', '.join(order_summary)}\n"
                f"Subtotal: ${validated_order.SubTotal}\n"
                f"Total with Tax: ${validated_order.Total}\n"
                f"Order ID: {saved_order.OrderID}\n"
            )
            logger.debug(
                f"[AdoraIntegration.place_order] Order placed successfully! Returning: {successful_order_response}"
            )

            # To avoid confusion to the user, because of differences between
            # the subtotal and applied coupons, the response is modified to
            # replace subtotal with the discount amount.
            if validated_order.SubTotal > validated_order.Total:
                successful_order_response = (
                    "Order placed successfully!\n"
                    "Here are the details of your order, list the item name:\n"
                    f"{', '.join(order_summary)}\n"
                    f"Discount: ${validated_order.Discount}\n"
                    f"Total with Tax: ${validated_order.Total}\n"
                    f"Order ID: {saved_order.OrderID}\n"
                )

            # Combine the summary of items with the total price
            return successful_order_response

        else:
            logger.debug(
                f"[AdoraIntegration.place_order] Failed to place order. Saved order ID: {saved_order.OrderID if saved_order else 'NO SAVED ORDER'}"
            )
            return "There was an issue placing the order. Please try again."
