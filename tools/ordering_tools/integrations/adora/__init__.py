import json
import time
from typing import Any, Literal

from agno.storage.agent.base import AgentStorage
from agno.storage.agent.session import AgentSession
from geopy.geocoders import Nominatim

from agent.legacy.storage import get_storage
from tools.ordering_tools.classes import FulfillmentStrategy, OrderItem
from tools.ordering_tools.integrations.adora.classes import (
    AdoraDeliveryAddress,
    AdoraOrderCalculationResult,
    AdoraOrderItem,
    AdoraOrderType,
)
from utils.log import logger

from . import _apis, _utils

ADORA_PAYMENT_URL = "https://pizzamyheart.adorapos.net/OnlineOrdering/OrderHubPayment/?storeKey={store_id}&orderId={order_id}"


class AdoraIntegration:
    def __init__(
        self,
        account_name: str,
        store_information: dict[str, str],
        adora_conversion_examples: dict[
            Literal["items", "sizes", "modifiers", "coupons"], dict[str, str]
        ] = {},
        cart_conversion_sys_prompt: str | list[str] = "",
        coupon_id: int | None = None,
    ):
        self.account_name = account_name
        self.api_key = _utils.get_adora_secret(account_name, "API_KEY")
        self.api_secret = _utils.get_adora_secret(account_name, "API_SECRET")
        self.store_information = store_information
        self.adora_conversion_examples = adora_conversion_examples
        self.cart_conversion_sys_prompt = cart_conversion_sys_prompt
        self.adora_coupon_id = coupon_id if coupon_id else 134

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
            bearer_token, self.store_information["store_id"], [adora_order_item], None
        )

        if isinstance(validated_order, AdoraOrderCalculationResult):
            return (
                "Step 1 :In the response to the user (content field of output), in your agent's tone, tell the user this was added: "
                + f"QUANTITY: {adora_order_item.quantity}, SIZE: {adora_order_item.size}, ITEM NAME: {adora_order_item.item_name}, "
                + f"with MODIFICATIONS: {adora_order_item.modifications} for PRICE: {validated_order.subTotal} to your cart.\n\n"
                + "Step 2: In a new line, show users the current cart with bullet points and DO NOT miscount the quantity of items."
                + "with the format of '{quantity} x {item_size} {item_name} with {modification} for {price}'.\n\n"
                + "Step 3: In the cart field of the structured output, add this item to the cart in this json format and DO NOT miscount the quantity of items: "
                + f"{{'itemName': {adora_order_item.item_name}',itemId': {adora_order_item.itemId}, 'quantity': {adora_order_item.quantity}, 'sizeId': {adora_order_item.sizeId}, 'modifiers': {adora_order_item.modifiers}, 'price': {adora_order_item.price}, 'comment': {adora_order_item.comment}, 'taxes': {adora_order_item.taxes}}}"
            )
        else:
            return "Failed to validate order."

    def get_wait_time(self) -> str:
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."
        wait_time = _apis.get_wait_time(
            bearer_token, self.store_information["store_id"]
        )
        if wait_time:
            return f"The estimated wait time is {wait_time} minutes."
        else:
            return f"Please call the store at {self.store_information['phone']} for the estimated wait time."

    def list_coupons(self):
        return "Share a polite message about no coupons available, but a 20% discount will be applied for using the Jimmy beta."

    def place_order(
        self, user_id: str, session_id: str, current_user_query: str
    ) -> str:
        logger.debug("[AdoraIntegration.place_order] Placing order...")
        logger.debug(f"[AdoraIntegration.place_order] user_id: {user_id}")
        logger.debug(f"[AdoraIntegration.place_order] session_id: {session_id}")
        logger.debug(
            f"[AdoraIntegration.place_order] current_user_query: {current_user_query}"
        )

        # chat history will be reversed later
        chat_history = [f"User message: {current_user_query}"]
        latest_cart = []

        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        logger.debug(
            f"[AdoraIntegration.place_order] Got bearer token: {bool(bearer_token)}"
        )
        if not bearer_token:
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        storage: AgentStorage = get_storage(self.account_name)
        session: AgentSession | None = storage.read(session_id, user_id)
        logger.debug(f"[AdoraIntegration.place_order] Got session: {bool(session)}")
        if session and session.memory and "runs" in session.memory:
            logger.debug(
                "[AdoraIntegration.place_order] Processing session memory runs"
            )
            for run in session.memory["runs"][::-1]:
                run_content = json.loads(run["response"]["content"])
                logger.debug(
                    f"[AdoraIntegration.place_order] Run content: {run_content}"
                )
                if run_content["placed_order_id"] != "":
                    logger.debug(
                        "[AdoraIntegration.place_order] Found previous order, stopping"
                    )
                    break  # stop at the most recent order placed

                # if there's no cart set yet and we found one, set the cart
                if not latest_cart and run_content["cart"]:
                    latest_cart = run_content["cart"]
                    logger.debug(
                        f"[AdoraIntegration.place_order] Found cart in memory: {latest_cart}"
                    )

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
        logger.debug(
            f"[AdoraIntegration.place_order] Chat history length: {len(chat_history)}"
        )

        # Load memories
        account_name = self.account_name
        memories = _utils.get_consumer_memory(account_name, user_id)
        logger.debug(f"[AdoraIntegration.place_order] Got memories: {bool(memories)}")
        memory_list = (
            "## Existing Memories\n"
            + "\n".join(f"- {memory.memory}" for memory in memories)
            if memories
            else ""
        )

        # Get fulfillment strategy
        fulfillment_strategy_obj = _utils.get_fulfillment_strategy(chat_history)
        logger.debug(
            f"[AdoraIntegration.place_order] Fulfillment strategy: {fulfillment_strategy_obj}"
        )
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
        logger.debug(
            f"[AdoraIntegration.place_order] Adora order type: {adora_order_type}"
        )

        # Get the delivery address if the fulfillment strategy is delivery
        delivery_address = (
            _utils.get_delivery_address(chat_history, memory_list)
            if fulfillment_strategy == FulfillmentStrategy.DELIVERY
            else None
        )
        logger.debug(
            f"[AdoraIntegration.place_order] Delivery address: {delivery_address}"
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
            return "Ask the user to provide their first name, last name, and phone number to place an order."

        missing_info = []
        if consumer.first_name == "N/A":
            missing_info.append("first name")
        if consumer.last_name == "N/A":
            missing_info.append("last name")
        if consumer.phone_number == "N/A":
            missing_info.append("phone number")
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
        # Set consumer email
        consumer.email = "adora.receipts@proactiveailab.com"

        # Get generic coupon
        # Previously it called the get_coupon function, but PMH decided on "secret coupon" for now.
        adora_coupon_id = self.adora_coupon_id  # Hardcoded secret coupon
        logger.debug(
            f"[OrderingTools.place_order] Adding secret coupon: {adora_coupon_id}"
        )

        # Get cart, if empty return the error message
        logger.debug(f"[AdoraIntegration.place_order] Latest cart: {latest_cart}")
        cart = _utils.convert_to_adora_item(latest_cart)
        logger.debug(f"[AdoraIntegration.place_order] Generic cart: {cart}")

        # If the structured output does not work
        if not cart:
            if isinstance(self.cart_conversion_sys_prompt, list):
                self.cart_conversion_sys_prompt = " ".join(
                    self.cart_conversion_sys_prompt
                )
            elif type(self.cart_conversion_sys_prompt) is not str:
                self.cart_conversion_sys_prompt = ""
            llmcart = _utils.get_cart_info(
                chat_history, self.cart_conversion_sys_prompt
            )
            menu = _apis.get_adora_menu(
                self.store_information["store_id"], bearer_token
            )
            if not menu:
                logger.error("[AdoraIntegration.place_order] Failed to get menu.")
                return "Failed to get menu, please try again."

            menu_maps = _utils.get_menu_maps(menu)
            modifier_weights_map = _utils.get_modifier_weights_map(menu)
            size_map = _utils.get_size_description_map(menu)

            if llmcart:
                for order_item in llmcart.cart_items:
                    order_item = OrderItem(
                        order_item.item_name,
                        order_item.size,
                        order_item.quantity,
                        order_item.modifications,
                    )
                    convert_item_success, adora_order_item = (
                        _utils.validate_and_convert_item(
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
                    )

                    if not convert_item_success and isinstance(adora_order_item, str):
                        logger.debug(
                            f"[AdoraIntegration.place_order] Failed to convert item {order_item}: {adora_order_item}"
                        )
                        return adora_order_item

                    if not isinstance(adora_order_item, AdoraOrderItem):
                        return "Failed to convert order item."

                    cart[order_item.item_name] = adora_order_item
                    logger.debug(
                        f"[AdoraIntegration.place_order] Successfully converted item: {order_item.item_name}"
                    )
        # If the cart is still empty
        if not cart:
            return (
                "Your cart is empty. Please add items to your cart to place an order."
            )

        adora_cart = list(cart.values())
        logger.debug(
            f"[AdoraIntegration.place_order] Adora cart length: {len(adora_cart)}"
        )
        # Get bearer token
        bearer_token = _apis.get_adora_pos_auth_token(self.api_key, self.api_secret)
        if not bearer_token:
            logger.error(
                "[AdoraIntegration.place_order] Failed to authenticate ordering tool."
            )
            return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

        order_summary = []  # List to hold the summary of items and their prices

        logger.debug(
            "[AdoraIntegration.place_order] Converting items to Adora order items..."
        )

        for adora_order_item in cart:
            item = cart[adora_order_item]
            order_summary.append(
                f"{adora_order_item if item.quantity == 1 else f'{item.quantity}x {adora_order_item}'}"
            )

        logger.debug(
            "[AdoraIntegration.place_order] Converted items to Adora order items."
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
            logger.debug(
                f"[AdoraIntegration.place_order] Geocoded location: {bool(geocoded_loc)}"
            )
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
                return "Please provide a valid state and zipcode."

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
            logger.debug(
                f"[AdoraIntegration.place_order] Address validation success: {validated_address_success}"
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
        wait_time = _apis.get_wait_time_with_strategy(
            bearer_token, self.store_information["store_id"], fulfillment_strategy.value
        )
        logger.debug(f"[AdoraIntegration.place_order] Wait time: {wait_time}")

        # get special instructions
        order_comment = _utils.get_special_instructions(chat_history) or ""

        # validate order
        logger.debug("[AdoraIntegration.place_order] Validating order...")
        validated_order = _apis.validate_order(
            bearer_token,
            self.store_information["store_id"],
            adora_cart,
            adora_coupon_id,
            adora_order_type,
            consumer,
            adora_delivery_address,
            order_comment,
        )

        logger.debug(
            f"[AdoraIntegration.place_order] Validated order: {validated_order}"
        )

        if not validated_order or not validated_order.key:
            return "Failed to validate order. Please try again."

        # save validated order in Adora system, get order ID
        logger.debug("[AdoraIntegration.place_order] Saving validated order...")
        saved_order = _apis.save_validated_order(bearer_token, validated_order.key)
        logger.debug(f"[AdoraIntegration.place_order] Saved order: {bool(saved_order)}")

        if not saved_order or not saved_order.orderID:
            return "Failed to place order. Please try again."

        # delay 1 second to allow Adora to synchronize the order
        time.sleep(1)

        # send credit card payment link to the consumer
        try:
            if saved_order:
                text_payment_url = ADORA_PAYMENT_URL.format(
                    store_id=self.store_information["store_id"],
                    order_id=saved_order.orderID,
                )
                successful_order_details = (
                    "For the information below, MUST show all of them in order\n"
                )

                successful_order_details += (
                    "Your order is pending!\n"
                    f"Please proceed to the payment link to complete your order: {text_payment_url}\n"
                    "Here are the details of your order, MUST list the item names + item size + modfications:\n"
                    f"{', '.join(order_summary)}\n"
                )

                # Type check
                if validated_order.subTotal is None or validated_order.total is None:
                    return "Failed to place order. Please try again."

                if order_comment and order_comment != "N/A":
                    successful_order_details += f"Comments: ${order_comment}\n"

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
                    f"Store Address: {self.store_information['address']}\n"
                )
                order_record = f"Order ID: {saved_order.orderID}, Total: ${validated_order.total}, Order items: {', '.join(order_summary)}"
                _utils.add_order_to_memory(account_name, user_id, order_record)
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
        return "The item was successfully removed from the order! Here is your current cart:"
