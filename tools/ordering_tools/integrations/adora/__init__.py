import json
import time
from typing import Any, Literal

from geopy.geocoders import Nominatim
from phi.agent.session import AgentSession
from phi.storage.agent.base import AgentStorage

from agent.storage import get_storage
from tools.ordering_tools.classes import FulfillmentStrategy, OrderItem
from tools.ordering_tools.integrations.adora.classes import (
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
        store_information: dict[str, str],
        adora_conversion_examples: dict[
            Literal["items", "sizes", "modifiers", "coupons"], dict[str, str]
        ] = {},
        cart_conversion_sys_prompt: str | list[str] = "",
    ):
        self.account_name = account_name
        self.api_key = _utils.get_adora_secret(account_name, "API_KEY")
        self.api_secret = _utils.get_adora_secret(account_name, "API_SECRET")
        self.store_information = store_information
        self.adora_conversion_examples = adora_conversion_examples
        self.cart_conversion_sys_prompt = cart_conversion_sys_prompt

    def add_to_order(self, order_item: OrderItem) -> str:
        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        # Get menu from knowledge base based on menu name
        menu = _apis.get_adora_menu(self.store_information["store_id"], bearer_token)
        if not menu:
            return "Failed to get menu, please try again."
        menu_maps = _utils.get_menu_maps(menu)
        modifier_weights_map = _utils.get_modifier_weights_map(menu)
        size_map = _utils.get_size_description_map(menu)

        convert_item_success, adora_order_item = _utils.validate_and_convert_item(
            order_item,
            menu_maps,
            modifier_weights_map,
            size_map,
            menu["modifiers"],
            menu["modifier_groups"],
            self.adora_conversion_examples.get("items", {}),
            self.adora_conversion_examples.get("sizes", {}),
            self.adora_conversion_examples.get("modifiers", {}),
        )
        if not convert_item_success and isinstance(adora_order_item, str):
            return adora_order_item  # this is an error string

        if not isinstance(adora_order_item, AdoraOrderItem):
            return "Failed to convert order item."

        # validate order
        validated_order = _apis.validate_order(
            bearer_token, self.store_information["store_id"], [adora_order_item], 0
        )

        if isinstance(validated_order, AdoraOrderCalculationResult):
            return f"In the response, include quantity: {adora_order_item.quantity}, size: {adora_order_item.size}, item_name: {adora_order_item.item_name}, with modifications: {adora_order_item.modifications} for price: {validated_order.subTotal} to your cart."
        else:
            return "Failed to validate order."

    def list_coupons(self):
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        coupons = _apis.list_coupons(bearer_token, self.store_information["store_id"])

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
        self, user_id: str, session_id: str, current_user_query: str
    ) -> str:
        logger.debug("[AdoraIntegration.place_order] Placing order...")

        # chat history will be reversed later
        chat_history = [f"User message: {current_user_query}"]

        storage: AgentStorage = get_storage(self.account_name)
        session: AgentSession | None = storage.read(session_id, user_id)
        if session and session.memory and "runs" in session.memory:
            for run in session.memory["runs"][::-1]:
                run_content = json.loads(run["response"]["content"])
                if run_content["placed_order_id"] != "":
                    break  # stop at the most recent order placed

                chat_history.append(
                    f"User message: {run['message']['content']}\n\nAgent message: {run_content['content']}"
                )

        if not chat_history:
            logger.error(
                "[AdoraIntegration.place_order] Failed to get chat history because chat_history is empty."
            )
            return "Failed to place order. Please try again."

        # Reverse chat history to restore original order of messages AFTER most recent order placed
        chat_history = chat_history[::-1]

        # Load memories
        account_name = self.account_name
        memories = _utils.get_consumer_memory(account_name, user_id)
        memory_list = (
            "## Existing Memories\n"
            + "\n".join(f"- {memory.memory}" for memory in memories)
            if memories
            else ""
        )

        # Get fulfillment strategy
        fulfillment_strategy_obj = _utils.get_fulfillment_strategy(chat_history)
        if (
            not fulfillment_strategy_obj
            or fulfillment_strategy_obj.strategy == FulfillmentStrategy.NA
        ):
            logger.debug(
                f"[OrderingTools.place_order] Missing fulfillment strategy: {fulfillment_strategy_obj}"
            )
            return "Ask the user to provide a fulfillment strategy to place an order, e.g., delivery, pickup."

        fulfillment_strategy = fulfillment_strategy_obj.strategy
        generic_fulfillment_conversion_to_adoramap = {
            FulfillmentStrategy.DELIVERY: AdoraOrderType.Delivery,
            FulfillmentStrategy.PICKUP: AdoraOrderType.TakeOut,
        }
        adora_order_type = generic_fulfillment_conversion_to_adoramap[
            fulfillment_strategy
        ]

        # Get the delivery address if the fulfillment strategy is delivery
        delivery_address = (
            _utils.get_delivery_address(chat_history, memory_list)
            if fulfillment_strategy == FulfillmentStrategy.DELIVERY
            else None
        )

        if (
            fulfillment_strategy == FulfillmentStrategy.DELIVERY
            and not delivery_address
        ):
            return "Please provide a complete delivery address."

        # Get consumer information
        consumer = _utils.get_consumer_info(chat_history, memory_list)
        logger.debug(f"[OrderingTools.place_order] Consumer: {consumer}")
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
            logger.debug(
                f"[OrderingTools.place_order] Missing consumer info: {missing_info}"
            )
            return (
                f"Please provide your {' and '.join(missing_info)} to place an order."
            )

        # Add a note to the customer's name to indicate that the order was placed via Jimmy
        if "(via Jimmy)" not in consumer.last_name:
            consumer.last_name += " (via Jimmy)"

        # Format phone number
        consumer.phone_number = "({}){}-{}".format(
            consumer.phone_number[:3],
            consumer.phone_number[3:6],
            consumer.phone_number[6:],
        )

        # Get generic coupon
        generic_coupon_info = _utils.get_generic_coupon_info(chat_history)
        generic_coupon = generic_coupon_info.coupon if generic_coupon_info else "N/A"
        logger.debug(f"[OrderingTools.place_order] Generic coupon: {generic_coupon}")

        # Get cart, if empty return the error message
        if isinstance(self.cart_conversion_sys_prompt, list):
            self.cart_conversion_sys_prompt = " ".join(self.cart_conversion_sys_prompt)
        elif type(self.cart_conversion_sys_prompt) is not str:
            self.cart_conversion_sys_prompt = ""
        cart = _utils.get_cart_info(chat_history, self.cart_conversion_sys_prompt)
        logger.debug(f"[AdoraIntegration.place_order] Generic cart: {cart}")

        if not cart:
            return "Your cart is empty. Please add items to your order."

        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            logger.error(
                "[AdoraIntegration.place_order] Failed to authenticate ordering tool."
            )
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        # Get up-to-date menu and construct order payload
        menu = _apis.get_adora_menu(self.store_information["store_id"], bearer_token)
        if not menu:
            logger.error("[AdoraIntegration.place_order] Failed to get menu.")
            return "Failed to get menu, please try again."

        menu_maps = _utils.get_menu_maps(menu)
        modifier_weights_map = _utils.get_modifier_weights_map(menu)
        size_map = _utils.get_size_description_map(menu)

        order_items = []
        order_summary = []  # List to hold the summary of items and their prices

        logger.debug(
            "[AdoraIntegration.place_order] Converting items to Adora order items..."
        )

        for order_item in cart.cart_items:
            order_item = OrderItem(
                order_item.item_name,
                order_item.size,
                order_item.quantity,
                order_item.modifications,
            )
            convert_item_success, adora_order_item = _utils.validate_and_convert_item(
                order_item,
                menu_maps,
                modifier_weights_map,
                size_map,
                menu["modifiers"],
                menu["modifier_groups"],
                self.adora_conversion_examples.get("items", {}),
                self.adora_conversion_examples.get("sizes", {}),
                self.adora_conversion_examples.get("modifiers", {}),
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
            possible_coupons = _apis.list_coupons(
                bearer_token, self.store_information["store_id"]
            )
            adora_coupon_res = _utils.convert_coupon(
                possible_coupons,
                generic_coupon,
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

        # validate address if delivery order
        adora_delivery_address = None
        if adora_order_type == AdoraOrderType.Delivery:
            if not delivery_address:
                return "Ask the user to provide a delivery address to place a delivery order."
            if delivery_address.address == "N/A" or delivery_address.city == "N/A":
                return "Ask the user to provide at least a street address and city."

            # setup Nominatim to convert address to lat long coordinates
            # TODO: Usage limited to 1qps without API key. Upgrade to paid plan when needed.
            # TODO: https://aws.amazon.com/location/
            geolocator = Nominatim(user_agent="pal")

            geo_payload = {
                "street": delivery_address.address,
                "city": delivery_address.city,
                "state": (
                    delivery_address.state if delivery_address.state != "N/A" else ""
                ),
                "country": "USA",
                "postalcode": (
                    delivery_address.zip_code
                    if delivery_address.zip_code != "N/A"
                    else ""
                ),
            }
            logger.debug(
                "[AdoraIntegration.place_order] Geolocator payload: " + str(geo_payload)
            )
            geocoded_loc: Any = geolocator.geocode(geo_payload)
            if not geocoded_loc:
                logger.debug(
                    "[AdoraIntegration.place_order] Failed to geocode address."
                )
                return (
                    "The address that the user provided is invalid. Please provide a valid address. "
                    + (
                        "Try providing a state and zipcode."
                        if delivery_address.state == "N/A"
                        or delivery_address.zip_code == "N/A"
                        else ""
                    )
                )

            logger.debug(
                "[AdoraIntegration.place_order] Nominatim API result: "
                + str(geocoded_loc.latitude)
                + ", "
                + str(geocoded_loc.longitude)
            )

            # auto-populate state and zipcode
            if delivery_address.state == "N/A" or delivery_address.zip_code == "N/A":
                delivery_address = _utils.convert_address_string(geocoded_loc.address)
                logger.debug(
                    f"[AdoraIntegration.place_order] Auto-populated address: {delivery_address}"
                )

            if (
                not delivery_address
                or delivery_address.address == "N/A"
                or delivery_address.city == "N/A"
                or delivery_address.state == "N/A"
                or delivery_address.zip_code == "N/A"
            ):
                logger.debug(
                    f"[AdoraIntegration.place_order] Failed to convert address. Delivery address object: {delivery_address}"
                )
                return "Something went wrong with delivery address conversion. Please try again."

            # call Adora address validation API
            validated_address_success, validated_address = _apis.validate_address(
                bearer_token,
                self.store_information["store_id"],
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
                typeId=validated_address[0].typeId,
            )
        # get wait time
        logger.debug("[AdoraIntegration.place_order] Getting the waiting time...")
        wait_time = _apis.get_wait_time(
            bearer_token, self.store_information["store_id"], fulfillment_strategy.value
        )

        # validate order
        logger.debug("[AdoraIntegration.place_order] Validating order...")
        validated_order = _apis.validate_order(
            bearer_token,
            self.store_information["store_id"],
            order_items,
            adora_coupon_id,
            adora_order_type,
            consumer,
            adora_delivery_address,
        )
        if not validated_order or not validated_order.key:
            return "Failed to validate order. Please try again."

        # save validated order in Adora system, get order ID
        logger.debug("[AdoraIntegration.place_order] Saving validated order...")
        saved_order = _apis.save_validated_order(bearer_token, validated_order.key)

        if not saved_order or not saved_order.orderID:
            return "Failed to place order. Please try again."

        # delay 1 second to allow Adora to synchronize the order
        time.sleep(1)

        # send credit card payment link to the consumer
        try:
            if saved_order and _apis.text_payment(
                bearer_token,
                saved_order.orderID,
                self.store_information["store_id"],
                consumer.phone_number,
            ):
                successful_order_details = (
                    "Order placed successfully!\n"
                    "Here are the details of your order, list the item names + prices:\n"
                    f"{', '.join(order_summary)}\n"
                )

                # Type check
                if validated_order.subTotal is None or validated_order.total is None:
                    return "Failed to place order. Please try again."

                # Add discount, otherwise add subtotal
                if validated_order.subTotal > validated_order.total:
                    successful_order_details += (
                        f"Discount: ${validated_order.discount}\n"
                    )
                else:
                    successful_order_details += (
                        f"Subtotal: ${validated_order.subTotal}\n"
                    )

                successful_order_details += (
                    f"Total with Tax: ${validated_order.total}\n"
                    f"Order ID: {saved_order.orderID}\n"
                    f"Store Phone: {self.store_information['phone']}\n"
                )
                if wait_time is not None and wait_time >= 30:
                    successful_order_details += (
                        f"Estimated wait time: {wait_time} minutes\n"
                    )

                logger.debug(
                    f"[AdoraIntegration.place_order] Order placed successfully! Returning: {successful_order_details}"
                )

                # Combine the summary of items with the total price
                return successful_order_details

            else:
                logger.debug(
                    f"[AdoraIntegration.place_order] Failed to place order. Saved order ID: {saved_order.orderID if saved_order else 'NO SAVED ORDER'}"
                )
                return "The service maybe busy. Please try again."
        except Exception as e:
            logger.error(
                f"[AdoraIntegration.place_order] Error returning placed order information back to user! Error: {e}"
            )
            return "Failed to place order. Please try again."

    def remove_from_order(self):
        return "The item was successfully removed from the order!"
