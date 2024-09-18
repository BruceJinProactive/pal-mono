import json
import re
from collections import defaultdict
from dataclasses import dataclass
from os import getenv
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from ai.tools.adapters.integrations.pos.adora_pos.adora_pos_apis import (
    AdoraCustomerInfo,
    AdoraPosDeliveryAddress,
    AdoraPosOrderCalculationResult,
    AdoraPosOrderType,
    calculate_tax_fees_and_total,
    submit_order_and_text_payment_link,
)
from ai.tools.ordering_classes import OrderItem

CART_JSON_PATH = "data/pizza/cart.json"

client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
OPENAI_CONVERSION_MODEL = "gpt-4o-2024-08-06"


# TODO: set up some error handling system.
# TODO: no longer mock cart, more Adora POS cart.


@dataclass
class ConversionResult:
    success: bool
    message: str


def convert_order_item_to_adora(order_item: OrderItem) -> ConversionResult:
    """
    Converts the order item to the Adora POS format.


    1. Find the closest item name in the menu and consequent item id.
    2. Map the size to size id.
    3. Map the modifications to modifiers and comments.
    4. Return the API payload required by Adora.
    """

    menu = {}
    with open("data/pizza/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
        menu = json.load(read_f)

    # Invalid quantity, temporary fix
    if order_item.quantity < 1:
        return ConversionResult(False, "Quantity must be at least 1.")
    if order_item.quantity > 100:
        return ConversionResult(False, "Quantity must be at most 100.")

    def get_adora_item_id(order_item_name: str) -> ConversionResult:
        """
        Finds the closest item name in the menu and consequent item id.
        """

        # Load menu item names
        menu_items = []
        for item in menu["items"]:
            menu_items.append(item["name"])

        # Get GPT to find the most similar item name
        sys_prompt = f"""# CONTEXT #
I am a waiter at a restaurant. I am taking a user's order. 
I want to match a user supplied item name to an item on the menu. 
Here are the menu items {menu_items}

#########

# OBJECTIVE #
Match the user's inputted item name to the closest item option on the menu as if you were a server/waiter.

#########

# EXAMPLES #
User: big sur
Assistant: Big Sur

User: cowels coombo
Assistant: Cowell's Combo

User: supreme pizza
Assistant: N/A

#########

# RESPONSE FORMAT #
Only output the most similar menu item name. Output "N/A" if the user's inputted item name is nothing like any of the available options.
"""
        response = client.chat.completions.create(
            model=OPENAI_CONVERSION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": sys_prompt,
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": order_item_name},
                    ],
                },
            ],
            temperature=0,
            max_tokens=256,
            response_format={"type": "text"},
        )

        item_name = response.choices[0].message.content
        for item in menu["items"]:
            if item["name"] == item_name:
                return ConversionResult(True, item["item_id"])

        return ConversionResult(False, "Item not found in menu.")

    def get_adora_size_id(adora_item_id: int, order_item_size: str) -> ConversionResult:
        """
        Maps the size to size id
        """
        # Size descriptions.
        # TODO: Make more comprehensive
        size_descriptions = {
            "1": '12"',
            "2": '14"',
            "3": '18"',
            "4": 'Gluten Free 12"',
            "5": "Heart Shaped",
            "6": "Regular",
            "16": "Pint",
            "17": "Pitcher",
            "18": "Bottle",
            "19": "6 Pack",
            "20": "Catering",
            "21": "6 Wings",
            "22": "12 Wings",
            "23": "24 Wings",
            "24": "Slices",
            "25": "Kids Make Pizza",
        }

        # Find available size ids for the item
        available_sizes: set = set()
        for item in menu["items"]:
            if item["item_id"] == adora_item_id:
                for size in item["order_types"][0]["sizes"]:
                    available_sizes.add(str(size["size_id"]))

        # Get GPT to find the most similar size
        size_options = []
        for size in available_sizes:
            size_options.append(size_descriptions[size])

        sys_prompt = f"""# CONTEXT #
I am a waiter at a restaurant. I am taking a user's order.
I want to match a user supplied item size to an available item size on the menu.
Here are the available size options {size_options}

#########

# OBJECTIVE #
Match the user's inputted item size to the closest item size on the menu as if you were a server/waiter.

#########

# EXAMPLES #
If the size options are 12", 14" and 18"
User: large
Assistant: 18"

User: medium
Assistant: 14"

User: 12-inch
Assistant: 12"

#########

# RESPONSE FORMAT #
Only output the most similar item size. Output "N/A" if the user's inputted item size is nothing like any of the available options.
"""
        response = client.chat.completions.create(
            model=OPENAI_CONVERSION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": sys_prompt,
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": order_item_size},
                    ],
                },
            ],
            temperature=0,
            max_tokens=256,
            response_format={"type": "text"},
        )

        item_size = response.choices[0].message.content
        for size_id, size in size_descriptions.items():
            if size == item_size:
                return ConversionResult(True, size_id)

        return ConversionResult(False, "Size not found in menu.")

    # TODO: Account for modifier weight. Default to "Regular" for now. Also figure out price field.
    def get_adora_modifications(
        adora_item_id: int, order_item_modifications: list
    ) -> ConversionResult:
        """
        Map the modifications to modifiers and comments.
        """
        # Logic to follow: If it's not a valid modifier, it's a comment.
        payload = {"comment": "", "modifiers": []}

        # Get the modifier groups for the item
        item_modifier_groups = []
        for item in menu["items"]:
            if item["item_id"] == adora_item_id:
                item_modifier_groups = item["modifier_groups"]
                break

        # Keep track of modifier group constraints
        modifier_group_counter: dict = defaultdict(int)
        # Initialize map for modifier id to group id for later
        modifier_id_to_group_id = {}

        # Add all default modifiers
        for item_modifier_group in item_modifier_groups:
            item_modifier_group_id = item_modifier_group["modifier_group_id"]
            item_modifier_group_modifiers = item_modifier_group["modifiers"]
            for item_modifier_group_modifier in item_modifier_group_modifiers:
                modifier_id_to_group_id[item_modifier_group_modifier["modifier_id"]] = (
                    item_modifier_group_id
                )
                if item_modifier_group_modifier["default"]:
                    payload["modifiers"].append(
                        {
                            "id": item_modifier_group_modifier["modifier_id"],
                            "isDefault": True,
                            "price": 1,
                            "weightId": 3,
                        }
                    )
                    modifier_group_counter[item_modifier_group_id] += 1

        modifier_names = []
        for modifier in menu["modifiers"]:
            modifier_names.append(modifier["name"])

        sys_prompt = f"""# CONTEXT #
I am a waiter at a restaurant. I am taking a user's order.
I want to match a user supplied item modification to an available item modification on the menu.
Here are the available modification options {modifier_names}

#########

# OBJECTIVE #
Match the user's inputted item modification to the closest item modification on the menu as if you were a server/waiter.

#########

# EXAMPLES #
User: anchoby
Assistant: Anchovy

User: extra cheese
Assistant: Extra Cheese

User: nutella
Assistant: N/A

#########

# RESPONSE FORMAT #
Only output the most similar item size. Output "N/A" if the user's inputted item size is nothing like any of the available options.
"""

        # 1. Iterate through the modifications and find most similar for each.
        for order_item_modification in order_item_modifications:
            response = client.chat.completions.create(
                model=OPENAI_CONVERSION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": sys_prompt,
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": order_item_modification,
                            },
                        ],
                    },
                ],
                temperature=0,
                max_tokens=256,
                response_format={"type": "text"},
            )

            most_similar_modifier_id = ""
            for modifier in menu["modifiers"]:
                if modifier["name"] == response.choices[0].message.content:
                    most_similar_modifier_id = modifier["modifier_id"]
                    break

            # If it's a valid modifier above a certain threshold, append to modifiers. Else, append to comment.
            # TODO: Figure out if we need to account for modifier weight or if it's done by API.
            if most_similar_modifier_id:
                # Check if it's a valid modifier for the item. Otherwise, return error.
                modifier_found = False
                for item_modifier_group in item_modifier_groups:
                    item_modifier_group_id = item_modifier_group["modifier_group_id"]
                    item_modifier_group_modifiers = item_modifier_group["modifiers"]
                    for item_modifier_group_modifier in item_modifier_group_modifiers:
                        adora_modifier = {
                            "id": most_similar_modifier_id,
                            "isDefault": item_modifier_group_modifier["default"],
                            "price": 1,
                            "weightId": 3,
                        }
                        if adora_modifier in payload["modifiers"]:  # Slow array search
                            modifier_found = True
                            break
                        if (
                            item_modifier_group_modifier["modifier_id"]
                            == most_similar_modifier_id
                        ):
                            payload["modifiers"].append(adora_modifier)
                            modifier_group_counter[item_modifier_group_id] += 1
                            modifier_found = True
                            break
                if not modifier_found:
                    return ConversionResult(
                        False, f"Modifier {order_item_modification} not valid for item."
                    )
            else:
                payload["comment"] += order_item_modification + ". "

        # 2. Check if all modifier group constraints have been satisfied.
        for modifier_group_id in modifier_group_counter.keys():
            for modifier_group in menu["modifier_groups"]:  # Slow array search
                if modifier_group["modifier_group_id"] == modifier_group_id:
                    # Heuristic: Assume defaults are there, if min==max==1 then take user provided/remove default
                    # Also assume there won't be two+ defaults in this case (assume doesn't default to invalid order)
                    # TODO: Optimize.
                    if (
                        modifier_group["min_required_modifier"] == 1
                        and modifier_group["max_allowed_modifier"] == 1
                        and modifier_group_counter[modifier_group_id] > 1
                    ):
                        adora_modifier_to_remove = None
                        for adora_modifier in payload["modifiers"]:
                            if (
                                adora_modifier["isDefault"]
                                and modifier_id_to_group_id[adora_modifier["id"]]
                                == modifier_group_id
                            ):
                                adora_modifier_to_remove = adora_modifier
                                break
                        payload["modifiers"].remove(adora_modifier_to_remove)
                        modifier_group_counter[modifier_group_id] -= 1
                    # If below min or above max, return appropriate error message
                    if (
                        modifier_group_counter[modifier_group_id]
                        < modifier_group["min_required_modifier"]
                    ):
                        return ConversionResult(
                            False,
                            f"Please provide at least {modifier_group['min_required_modifier']} modifiers for {modifier_group['name']}.",
                        )
                    if (
                        modifier_group_counter[modifier_group_id]
                        > modifier_group["max_allowed_modifier"]
                    ):
                        return ConversionResult(
                            False,
                            f"Please provide at most {modifier_group['max_allowed_modifier']} modifiers for {modifier_group['name']}.",
                        )

        return ConversionResult(True, json.dumps(payload))

    # Main logic begins here
    adora_item_id_res = get_adora_item_id(order_item.item_name)
    if not adora_item_id_res.success:
        return adora_item_id_res

    adora_size_id_res = get_adora_size_id(
        int(adora_item_id_res.message), order_item.size
    )
    if not adora_size_id_res.success:
        return adora_size_id_res

    adora_modifications_res = get_adora_modifications(
        int(adora_item_id_res.message),
        order_item.modifications,
    )
    if not adora_modifications_res.success:
        return adora_modifications_res
    adora_modifications_message_json = json.loads(adora_modifications_res.message)

    payload = {
        "itemId": int(adora_item_id_res.message),
        "sizeId": int(adora_size_id_res.message),
        "quantity": order_item.quantity,
        "comment": adora_modifications_message_json["comment"],
        "modifiers": adora_modifications_message_json["modifiers"],
        "price": 0,
        "taxes": [],
    }

    return ConversionResult(True, json.dumps(payload))


def _get_store_id() -> str:
    """
    Returns store id
    """
    return "9WHCV"


def convert_phone_number_to_adora(phone_number: str) -> str:
    """
    Converts phone number to Adora format
    """
    # GPT code from Max
    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone_number)

    # Check if the resulting string has 10 digits
    if len(digits) != 10:
        raise ValueError("Phone number must contain exactly 10 digits.")

    # Format the string into (xxx)xxx-xxxx
    formatted_number = f"({digits[:3]}){digits[3:6]}-{digits[6:]}"
    return formatted_number


class Cart(BaseModel):
    list_of_cart_items: list[dict] = []
    user: AdoraCustomerInfo
    store_id: str = _get_store_id()
    order_type: Optional[AdoraPosOrderType] = None
    address_for_delivery: Optional[AdoraPosDeliveryAddress] = None
    # tried_to_place_order: bool = False


def load_mock_cart(user_id: str) -> Cart:
    """
    Placeholder for now: Load the cart.json file.
    """

    cart = None
    with open(CART_JSON_PATH, "r") as read_f:
        carts = json.load(read_f)
        if user_id in carts:
            try:
                cart = Cart.model_validate(carts[user_id])
            except ValidationError as e:
                print(e)

    if not cart:
        cart = Cart(
            list_of_cart_items=[],
            user=AdoraCustomerInfo(
                first_name="", last_name="", email="", phone_number=""
            ),
        )

    return cart


def save_mock_cart(cart: Cart, user_id: str):
    """
    Placeholder for now: Save the cart.json file.
    """
    carts = {}
    with open(CART_JSON_PATH, "r") as read_f:
        carts = json.load(read_f)

    carts[user_id] = cart.model_dump()

    with open(CART_JSON_PATH, "w") as write_f:
        json.dump(carts, write_f, ensure_ascii=False, indent=4)


def get_adora_list_of_items(cart: Cart) -> list:
    """
    Extracts the Adora POS items from the cart.
    """
    adora_list = []
    for item in cart.list_of_cart_items:
        adora_list.append(item["pos_item"])

    return adora_list


def get_non_adora_list_of_items(cart: Cart) -> list:
    """
    Extracts all non-Adora POS items from the cart.
    """
    non_adora_list = []
    for item in cart.list_of_cart_items:
        non_adora_list.append(
            {
                "item_name": item["item_name"],
                "size": item["size"],
                "quantity": item["quantity"],
                "modifications": item["modifications"],
            }
        )

    return non_adora_list


def _calculate_order_info(cart: Cart) -> Optional[AdoraPosOrderCalculationResult]:
    """
    Calculate the order info.
    """

    return calculate_tax_fees_and_total(cart.store_id, get_adora_list_of_items(cart))


def _submit_order_to_adora(
    user_id: str, cart: Cart
) -> Optional[AdoraPosOrderCalculationResult]:
    """
    Submit the order to Adora.
    """

    order_info = submit_order_and_text_payment_link(
        cart.store_id,
        cart.user,
        get_adora_list_of_items(cart),
        # default to delivery if order type is not specified
        order_type=cart.order_type if cart.order_type else AdoraPosOrderType.TakeOut,
        # only specify delivery address if order type is delivery
        delivery_address=(
            cart.address_for_delivery
            if (cart.order_type and cart.address_for_delivery)
            else None
        ),
    )

    if order_info:
        reset_mock_cart(user_id)

    return order_info


def _get_order_update_string(cart: Cart) -> str:
    """
    Get the order update string.
    """
    order_total_string = ""
    order_calculation_result = _calculate_order_info(cart)
    if order_calculation_result:
        order_total_string = (
            f"Tell user the order total is ${order_calculation_result.Total}. "
        )

    return order_total_string


def _get_missing_order_info_prompt_from_cart(cart: Cart) -> str:
    """
    Get the missing user info from the mock cart.
    """
    # check missing user profile info
    missing_user_profile_info = "first name, " if cart.user.first_name == "" else ""
    missing_user_profile_info += "last name, " if cart.user.last_name == "" else ""
    missing_user_profile_info += "email, " if cart.user.email == "" else ""
    missing_user_profile_info += (
        "phone number, " if cart.user.phone_number == "" else ""
    )
    missing_user_profile_info_prompt = (
        f"Ask user for their {missing_user_profile_info} since the user will need them to checkout. "
        if missing_user_profile_info != ""
        else ""
    )

    # check if it's delivery or not, and ask for delivery address if it's delivery and address is missing
    missing_delivery_info = ""
    if cart.order_type is None:
        missing_delivery_info += (
            "Ask the user if he like to pick up the order or have it delivered. "
        )
    # TODO: Add checking other parts of address
    elif cart.order_type == AdoraPosOrderType.Delivery:
        if cart.address_for_delivery is None:
            missing_delivery_info += (
                "Ask the user for the delivery address with zip code. "
            )
        else:
            missing_address_parts = ""
            if cart.address_for_delivery.address == "":
                missing_address_parts += (
                    "street address, and apartment or unit number if any, "
                )
            if cart.address_for_delivery.city == "":
                missing_address_parts += "city, "
            if cart.address_for_delivery.state == "":
                missing_address_parts += "state, "
            if cart.address_for_delivery.zip == "":
                missing_address_parts += "zip code, "
            if missing_address_parts != "":
                missing_delivery_info += f"Ask the user for the delivery address with {missing_address_parts} "

    missing_info_prompt = missing_user_profile_info_prompt + missing_delivery_info

    return missing_info_prompt


def _get_order_item_list_prompt(cart: Cart) -> str:
    """
    Get the order item list prompt.
    """
    order_item_list_prompt = ""
    if cart.list_of_cart_items:
        order_item_list_prompt = (
            "Tell user he has the list of below in the order.\n "
            + json.dumps(get_non_adora_list_of_items(cart))
        )

    return order_item_list_prompt


def _get_tool_response_prompt(order_update_string: str, cart: Cart) -> str:
    """
    Get the order update prompt.
    """
    order_total_string = _get_order_update_string(cart)
    missing_order_info_prompt = _get_missing_order_info_prompt_from_cart(cart)
    order_item_list_prompt = _get_order_item_list_prompt(cart)

    tool_response = (
        missing_order_info_prompt
        + order_update_string
        + order_total_string
        + order_item_list_prompt
    )
    return tool_response


def set_user_info_to_mock_cart(
    user_id: str, first_name: str, last_name: str, email: str, phone_number: str
) -> str:
    """
    Sets the user info to the mock cart.
    """
    cart = load_mock_cart(user_id)

    if first_name != "":
        cart.user.first_name = first_name

    if last_name != "":
        cart.user.last_name = last_name

    if email != "":
        cart.user.email = email

    if phone_number != "":
        try:
            cart.user.phone_number = convert_phone_number_to_adora(phone_number)
        except ValueError as e:
            return str(e)

    save_mock_cart(cart, user_id)

    return "User info updated successfully."


def set_order_type_to_mock_cart(user_id: str, order_type: str) -> str:
    """
    Sets the order type to the mock cart
    """
    cart = load_mock_cart(user_id)

    order_type = order_type.lower()
    if order_type == "delivery":
        order_type_enum = AdoraPosOrderType.Delivery
    else:
        order_type_enum = AdoraPosOrderType.TakeOut

    cart.order_type = order_type_enum

    save_mock_cart(cart, user_id)

    return_prompt = "Order type updated successfully."

    return return_prompt


def set_delivery_address_to_mock_cart(
    user_id: str, address: str, extended_address: str, city: str, state: str, zip: str
) -> str:
    """
    Sets the user's delivery address to the mock cart
    """
    cart = load_mock_cart(user_id)

    adora_delivery_address: AdoraPosDeliveryAddress = (
        cart.address_for_delivery
        if cart.address_for_delivery
        else AdoraPosDeliveryAddress(
            address="", extendedAddress="", city="", state="", zip=""
        )
    )

    # only update if not empty string
    if address != "":
        adora_delivery_address.address = address
    if extended_address != "":
        adora_delivery_address.extendedAddress = extended_address
    if city != "":
        adora_delivery_address.city = city
    if state != "":
        adora_delivery_address.state = state
    if zip != "":
        adora_delivery_address.zip = zip

    cart.address_for_delivery = adora_delivery_address

    save_mock_cart(cart, user_id)

    return "Delivery address updated successfully."


def add_mock_cart(user_id: str, order_item: OrderItem) -> str:
    """
    Adds an order item to the mock cart.
    """

    cart = load_mock_cart(user_id)

    # convert the order into Adora POS format
    adora_order_item_res = convert_order_item_to_adora(order_item)
    if not adora_order_item_res.success:
        return adora_order_item_res.message
    adora_order_item = json.loads(adora_order_item_res.message)
    cart_order_item = {
        "item_name": order_item.item_name,
        "size": order_item.size,
        "quantity": order_item.quantity,
        "modifications": order_item.modifications,
        "pos_item": adora_order_item,
    }

    cart.list_of_cart_items.append(cart_order_item)

    save_mock_cart(cart, user_id)

    if adora_order_item:
        return _get_tool_response_prompt(
            f"Added {order_item.item_name} to your cart. ", cart
        )
    else:
        return "Tell user we cannot find that item from the menu."


def remove_mock_cart(user_id: str, order_item: OrderItem) -> str:
    """
    Removes an order item from the mock cart
    """
    cart = load_mock_cart(user_id)

    # convert the order into Adora POS format
    adora_order_item_res = convert_order_item_to_adora(order_item)
    if not adora_order_item_res.success:
        return adora_order_item_res.message
    adora_order_item = json.loads(adora_order_item_res.message)
    cart_order_item = {
        "item_name": order_item.item_name,
        "size": order_item.size,
        "quantity": order_item.quantity,
        "modifications": order_item.modifications,
        "pos_item": adora_order_item,
    }

    if cart_order_item in cart.list_of_cart_items:
        cart.list_of_cart_items.remove(cart_order_item)

        save_mock_cart(cart, user_id)

        return _get_tool_response_prompt(
            f"Removed {order_item.item_name} from your cart. ", cart
        )
    else:
        return "Tell user we cannot find that item in the cart."


def get_mock_cart(user_id) -> str:
    """
    Returns cart information.
    """
    cart = load_mock_cart(user_id)

    # Heuristic: User has cart items <=> User wants to order
    if not cart.list_of_cart_items:
        return ""

    return _get_tool_response_prompt("Abide by the following instructions: ", cart)


def checkout_mock_cart(user_id) -> str:
    """
    Places order and returns corresponding prompt
    """
    cart = load_mock_cart(user_id)

    missing_order_info_prompt = _get_missing_order_info_prompt_from_cart(cart)
    if missing_order_info_prompt != "":
        return (
            "let user know need more information to checkout. "
            + missing_order_info_prompt
        )

    order_info = _submit_order_to_adora(user_id, cart)

    if order_info:
        total_price = order_info.Total
        return f"Tell user the total is going to be ${total_price} with tax and fees and tell user we sent a text message to his phone number to finish the payment to finalize the order."
    else:
        return "There was an issue with your order. Please try again later."


def reset_mock_cart(user_id):
    """
    Placeholder for now: Reset the cart.json file.
    """
    cart = load_mock_cart(user_id)

    cart.list_of_cart_items = []

    cart.order_type = None

    save_mock_cart(cart, user_id)


def hard_reset_mock_cart(user_id):
    """
    Completely removes the user from the cart.json file
    """
    carts = {}
    with open(CART_JSON_PATH, "r") as read_f:
        carts = json.load(read_f)

    if user_id in carts:
        carts.pop(user_id)

    with open(CART_JSON_PATH, "w") as write_f:
        json.dump(carts, write_f, ensure_ascii=False, indent=4)
