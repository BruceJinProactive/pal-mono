from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ai.tools.ordering_tools.classes import OrderItem
from ai.tools.ordering_tools.integrations.adora.classes import (
    AdoraCoupon,
    AdoraOrderItem,
)

# Size descriptions.
# TODO: Make more comprehensive
SIZE_DESCRIPTION_MAP = {
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


@dataclass
class ConversionResult:
    success: bool
    message: str


def convert_coupon(
    all_coupons: list[AdoraCoupon], target_coupon: str, openai_client, openai_model: str
) -> AdoraCoupon | None:
    """Given a list of all available coupons and a target coupon, convert the target coupon to a Coupon object.

    Args:
        all_coupons (list[Coupon]): A list of all available coupons as Coupon objects.
        target_coupon (str): The target coupon to convert.
        openai_client (OpenAI): The OpenAI client to use for the coupon conversion.
        openai_model (str): The OpenAI model to use for the coupon conversion.

    Returns:
        AdoraCoupon | None: The converted Coupon object if the target coupon was found in the list of all coupons.
    """

    message = (
        "\n\n".join([f"{c.id}\n{c.name}\n{c.description}" for c in all_coupons])
        + "\n\n\nTARGET COUPON:\n"
        + target_coupon
    )

    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """You are given a list of available coupons.
                        An available coupon has an ID, a name, and a description.
                        Convert the user's target coupon to a valid coupon from the list.
                        The target coupon will be at the bottom of the message.
                        Output the target coupon in the desired format.
                        If the target coupon does not match any available coupons, then
                            output 0 in the ID field and "N/A" in the name and description fields.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{message}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=AdoraCoupon,
    )

    return response.choices[0].message.parsed


def get_adora_item_id(
    menu: dict, order_item_name: str, openai_client, openai_model: str
) -> ConversionResult:
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
    response = openai_client.chat.completions.create(
        model=openai_model,
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


def get_adora_item_name(menu: dict, adora_item_id: int) -> str | None:
    """
    Retrieve the name of an item from the Adora menu.

    Args:
        menu (dict): A dictionary representing the menu, which contains a list of items.
        adora_item_id (int): The unique identifier of the Adora item.

    Returns:
        str | None: The name of the Adora item if found, otherwise None.
    """
    for item in menu["items"]:
        if item["item_id"] == adora_item_id:
            return item["name"]
    return None


def get_adora_size_id(
    menu, adora_item_id: int, order_item_size: str, openai_client, openai_model: str
) -> ConversionResult:
    """
    Maps the size to size id.
    """
    # Find available size ids for the item
    available_sizes: set = set()
    for item in menu["items"]:
        if item["item_id"] == adora_item_id:
            for size in item["order_types"][0]["sizes"]:
                available_sizes.add(str(size["size_id"]))

    # Get GPT to find the most similar size
    size_options = []
    for size in available_sizes:
        size_options.append(SIZE_DESCRIPTION_MAP[size])

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

User: small
Assistant: 12"

User: 12 inch
Assistant: 12"

#########

# RESPONSE FORMAT #
Only output the most similar item size. Output "N/A" if the user's inputted item size is nothing like any of the available options.
"""
    response = openai_client.chat.completions.create(
        model=openai_model,
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
    for size_id, size in SIZE_DESCRIPTION_MAP.items():
        if size == item_size:
            return ConversionResult(True, size_id)

    return ConversionResult(False, "Size not found in menu.")


def get_similar_modifier_using_openai(
    openai_client: OpenAI,
    openai_model: str,
    order_item_modification: str,
    modifier_names: list,
) -> str | None:
    """
    Uses OpenAI's language model to match a user-supplied item modification to the most similar modifier on the menu.

    Args:
        openai_client (OpenAI): The OpenAI client instance used for interacting with the OpenAI API.
        openai_model (str): The OpenAI model name (e.g., "gpt-4") used to generate completions.
        order_item_modification (str): The user-provided modification for an order item (e.g., "extra cheese").
        modifier_names (list): A list of available modifier names on the menu.

    Returns:
        str: The most similar modifier from the menu or "N/A" if no close match is found.
    """

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
Only output the most similar item modification. Output "N/A" if the user's inputted item modification is nothing like any of the available options.
"""
    response = openai_client.chat.completions.create(
        model=openai_model,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": order_item_modification},
        ],
        temperature=0,
        max_tokens=256,
    )

    return response.choices[0].message.content


def get_item_modifier_groups(menu: dict, adora_item_id: int) -> list:
    """
    Retrieves the modifier groups for a specific item from the menu.

    Args:
        menu (dict): The restaurant's menu data, containing items and their respective modifier groups.
        adora_item_id (int): The ID of the item for which modifier groups are being retrieved.

    Returns:
        list: A list of modifier groups for the specified item. If the item is not found, an empty list is returned.
    """

    for item in menu["items"]:
        if item["item_id"] == adora_item_id:
            return item["modifier_groups"]
    return []


def process_modifiers(
    menu: dict, order_item_modifications: list, openai_client: OpenAI, openai_model: str
) -> tuple[list, str]:
    """
    Processes user-supplied order item modifications, classifying them as valid modifiers or comments.

    Args:
        menu (dict): The restaurant's menu data, containing items and modifiers.
        order_item_modifications (list): A list of modifications provided by the user for a specific order item.
        openai_client (OpenAI): The OpenAI client instance used for interacting with the OpenAI API.
        openai_model (str): The OpenAI model name (e.g., "gpt-4") used to generate completions.

    Returns:
        tuple[list, str]:
            - A list of valid modifier IDs matched to the menu modifiers.
            - A comment string containing the user-provided modifications that did not match any menu modifiers.
    """
    modifier_names = [modifier["name"] for modifier in menu["modifiers"]]
    modifiers = []
    comment = ""

    for order_item_modification in order_item_modifications:
        matched_modifier = get_similar_modifier_using_openai(
            openai_client, openai_model, order_item_modification, modifier_names
        )

        most_similar_modifier_id = next(
            (
                modifier["modifier_id"]
                for modifier in menu["modifiers"]
                if modifier["name"] == matched_modifier
            ),
            None,
        )

        if most_similar_modifier_id:
            modifiers.append(most_similar_modifier_id)
        else:
            comment += order_item_modification + ". "

    return modifiers, comment


def validate_modifier_group_constraints(
    modifier_group_counter: dict, menu: dict, payload: dict
) -> tuple[bool, str]:
    """
    Validates that the modifier group constraints (e.g., minimum and maximum allowed modifiers) are satisfied.

    Args:
        modifier_group_counter (dict): A dictionary that tracks how many modifiers have been selected for each modifier group.
        menu (dict): The restaurant's menu data, containing the modifier groups and their constraints.
        payload (dict): The order payload that contains the list of selected modifiers.

    Returns:
        tuple[bool, str]:
            - A boolean indicating whether all modifier group constraints are satisfied.
            - A string containing an error message if the constraints are not met, otherwise an empty string.
    """

    modifier_group_dict = {
        mg["modifier_group_id"]: mg for mg in menu["modifier_groups"]
    }

    for modifier_group_id, count in modifier_group_counter.items():
        if modifier_group_id in modifier_group_dict:
            mg = modifier_group_dict[modifier_group_id]
            if count < mg["min_required_modifier"]:
                return (
                    False,
                    f"Please provide at least {mg['min_required_modifier']} modifiers for {mg['name']}.",
                )
            if count > mg["max_allowed_modifier"]:
                return (
                    False,
                    f"Please provide at most {mg['max_allowed_modifier']} modifiers for {mg['name']}.",
                )

    return True, ""


def get_adora_modifications(
    adora_item_name: str,
    adora_item_id: int,
    adora_size_name: str,
    adora_size_id: int,
    menu: dict,
    openai_client: OpenAI,
    openai_model: str,
    order_item: OrderItem,
    order_item_modifications: list,
) -> tuple[bool, AdoraOrderItem | str]:
    """
    Maps user-supplied modifications to a specific item in the restaurant's menu, handling both valid modifiers and comments.

    Args:
        adora_item_name (str): The name of the item in the Adora menu.
        adora_item_id (int): The ID of the item in the Adora menu.
        adora_size_name (str): The name of the size in the Adora menu.
        adora_size_id (int): The ID of the size in the Adora menu.
        menu (dict): The restaurant's menu data, containing items, modifier groups, and modifiers.
        openai_client (OpenAI): The OpenAI client instance used for interacting with the OpenAI API.
        openai_model (str): The OpenAI model name (e.g., "gpt-4") used to generate completions.
        order_item (OrderItem): The order item object that holds details such as quantity.
        order_item_modifications (list): A list of modifications provided by the user for the order item.

    Returns:
        tuple[bool, AdoraOrderItem | str]:
            - A boolean indicating whether the modifications were successfully applied.
            - An AdoraOrderItem object if successful, or an error message if a validation error occurred.
    """

    # Initialize payload
    payload = {"comment": "", "modifiers": []}

    # Get modifier groups for the item
    item_modifier_groups = get_item_modifier_groups(menu, adora_item_id)
    if not item_modifier_groups:
        return False, "No modifier groups found for item."

    # Process order item modifications using OpenAI
    modifiers, comment = process_modifiers(
        menu, order_item_modifications, openai_client, openai_model
    )
    payload["comment"] = comment

    # Add all default modifiers and track modifier group constraints
    modifier_group_counter = defaultdict(int)
    modifier_id_to_group_id = {}

    for item_modifier_group in item_modifier_groups:
        item_modifier_group_id = item_modifier_group["modifier_group_id"]
        for modifier in item_modifier_group["modifiers"]:
            modifier_id_to_group_id[modifier["modifier_id"]] = item_modifier_group_id
            if modifier["default"]:
                payload["modifiers"].append(
                    {
                        "id": modifier["modifier_id"],
                        "isDefault": True,
                        "price": 1,
                        "weightId": 3,
                    }
                )
                modifier_group_counter[item_modifier_group_id] += 1

    # Validate modifier group constraints
    is_valid, validation_message = validate_modifier_group_constraints(
        modifier_group_counter, menu, payload
    )
    if not is_valid:
        return False, validation_message

    adora_order_item = AdoraOrderItem(
        adora_item_id,
        adora_size_id,
        order_item.quantity,
        payload["comment"],
        0,
        payload["modifiers"],
    )

    adora_order_item.item_name = adora_item_name
    adora_order_item.size = adora_size_name
    adora_order_item.quantity = order_item.quantity
    # TODO: add modifications to the response
    # But this includes the whole modifier group and not the modifications
    # the user asked for and is incompatible to render as it's the wrong format
    # adora_order_item.modifications = ???

    return True, adora_order_item


def validate_and_convert_item(
    order_item: OrderItem, menu: Any, openai_client: OpenAI, openai_model: str
) -> tuple[bool, AdoraOrderItem | str]:
    """Converts a generic order item into an Adora order item.

    Args:
        order_item (OrderItem): The generic order item to convert.
        menu (object): The menu to use to get the item ID and size ID.
        openai_client (OpenAI): The OpenAI client to use for the item and size ID conversion.
        openai_model (str): The OpenAI model to use for the item and size ID conversion.

    Returns:
        tuple[bool, AdoraOrderItem | str]: A tuple containing a boolean indicating
            if the conversion was successful, and either the converted Adora order item or an error message.
    """
    # detect invalid quantity
    if order_item.quantity < 1:
        return False, f"{order_item.item_name}: Quantity must be at least 1."
    if order_item.quantity > 100:
        return False, f"{order_item.item_name}: Quantity must be at most 100."

    # get Adora-specific item id
    adora_item_id_res = get_adora_item_id(
        menu, order_item.item_name, openai_client, openai_model
    )
    if not adora_item_id_res.success:
        return False, adora_item_id_res.message
    adora_item_id = int(adora_item_id_res.message)

    # get Adora-specific item name
    adora_item_name = get_adora_item_name(menu, adora_item_id)
    if adora_item_name is None:
        return False, "Failed to get item in the menu."

    # get Adora-specific size id
    adora_size_id_res = get_adora_size_id(
        menu,
        adora_item_id,
        order_item.size,
        openai_client,
        openai_model,
    )
    if not adora_size_id_res.success:
        return False, adora_size_id_res.message
    adora_size_id = int(adora_size_id_res.message)

    # get Adora-specific size name
    adora_size_name = SIZE_DESCRIPTION_MAP.get(str(adora_size_id))
    if adora_size_name is None:
        return False, "Failed to get size of item in the menu."

    # get Adora-specific modifications and create the AdoraOrderItem
    adora_modifications_res = get_adora_modifications(
        adora_item_name,
        adora_item_id,
        adora_size_name,
        adora_size_id,
        menu,
        openai_client,
        openai_model,
        order_item,
        order_item.modifications,
    )

    return adora_modifications_res
