from collections import defaultdict
from dataclasses import dataclass

from openai import OpenAI

from ai.tools.ordering_tools.classes import OrderItem
from ai.tools.ordering_tools.integrations.adora.classes import (
    AdoraCoupon,
    AdoraOrderItem,
    MenuItemDetails,
)


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
    menu_name_to_id_map: dict, order_item_name: str, openai_client, openai_model: str
) -> ConversionResult:
    """
    Finds the closest item name in the menu and consequent item id.
    """
    # Load menu item names

    # Get GPT to find the most similar item name
    sys_prompt = f"""# CONTEXT #
I am a waiter at a restaurant. I am taking a user's order. 
I want to match a user supplied item name to an item on the menu. 
Here are the menu items {list(menu_name_to_id_map.keys())}

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
    if item_name in menu_name_to_id_map:
        return ConversionResult(True, menu_name_to_id_map[item_name])

    return ConversionResult(False, "Item not found in menu.")


def get_adora_size_id(
    menu_id_to_details_map: dict[int, MenuItemDetails],
    size_map: dict[int, str],
    adora_item_id: int,
    order_item_size: str,
    openai_client,
    openai_model: str,
) -> ConversionResult:
    """
    Maps the size to size id.
    """
    print("get_adora_size_id.size_map", size_map)

    # Find available size ids for the item
    available_sizes: set = set()
    if adora_item_id in menu_id_to_details_map:
        for size in menu_id_to_details_map[adora_item_id].order_types[0]["sizes"]:
            available_sizes.add(size["size_id"])

    print("available_sizes", available_sizes)

    # Get GPT to find the most similar size
    size_options = []
    for size in available_sizes:
        size_options.append(size_map[size])

    print("size_options", size_options)

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
    for size_id, size in size_map.items():
        if size == item_size:
            return ConversionResult(True, str(size_id))

    return ConversionResult(False, "Size not found in menu.")


def get_menu_maps(menu: dict) -> tuple[dict[int, MenuItemDetails], dict[str, int]]:
    """
    Extracts the item ID to details and name to ID maps from the menu data.

    Args:
        menu (dict): The menu data containing the items.

    Returns:
        tuple[dict, dict]: A tuple containing two dictionaries:
            - A dictionary mapping item IDs to their corresponding details.
            - A dictionary mapping item names to their corresponding IDs.
    """
    id_to_details_map = {
        item["item_id"]: MenuItemDetails(
            item["name"],
            item["order_types"] if "order_types" in item else [],
            item["modifier_groups"] if "modifier_groups" in item else [],
        )
        for item in menu["items"]
    }
    name_to_id_map = {item["name"]: item["item_id"] for item in menu["items"]}
    return id_to_details_map, name_to_id_map


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


def get_size_description_map(menu) -> dict[int, str]:
    """
    Extracts the size description map from the menu data.

    Args:
        menu (dict): The menu data containing the size descriptions.

    Returns:
        dict: A dictionary mapping size IDs to their corresponding descriptions.
    """
    return {size["size_id"]: size["name"] for size in menu["sizes"]}


def process_modifiers(
    menu_modifiers: dict,
    order_item_modifications: list,
    openai_client: OpenAI,
    openai_model: str,
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
    modifier_names = [modifier["name"] for modifier in menu_modifiers]
    modifiers = []
    comment = ""

    for order_item_modification in order_item_modifications:
        matched_modifier = get_similar_modifier_using_openai(
            openai_client, openai_model, order_item_modification, modifier_names
        )

        most_similar_modifier_id = next(
            (
                modifier["modifier_id"]
                for modifier in menu_modifiers
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
    modifier_group_counter: dict, menu_modifier_groups: dict, payload: dict
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

    modifier_group_dict = {mg["modifier_group_id"]: mg for mg in menu_modifier_groups}

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
    menu_id_to_details_map: dict[int, MenuItemDetails],
    menu_modifiers: dict,
    menu_modifier_groups: dict,
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
    item_modifier_groups = []
    if adora_item_id in menu_id_to_details_map:
        item_modifier_groups = menu_id_to_details_map[adora_item_id].modifier_groups
    if not item_modifier_groups:
        return False, "No modifier groups found for item."

    # Process order item modifications using OpenAI
    modifiers, comment = process_modifiers(
        menu_modifiers, order_item_modifications, openai_client, openai_model
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

    # Add user-provided modifiers to payload and update group counts
    for modifier_id in modifiers:
        payload["modifiers"].append(
            {
                "id": modifier_id,
                "isDefault": False,
                "price": 1,  # adjust the price as needed
                "weightId": 3,  # adjust the weightId as needed
            }
        )
        if modifier_id in modifier_id_to_group_id:
            modifier_group_counter[modifier_id_to_group_id[modifier_id]] += 1

    # Validate modifier group constraints
    is_valid, validation_message = validate_modifier_group_constraints(
        modifier_group_counter, menu_modifier_groups, payload
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
    order_item: OrderItem,
    menu_maps: tuple[dict[int, MenuItemDetails], dict[str, int]],
    size_map: dict[int, str],
    menu_modifiers: dict,
    menu_modifier_groups: dict,
    openai_client: OpenAI,
    openai_model: str,
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
    menu_id_to_details_map, menu_name_to_id_map = menu_maps
    # detect invalid quantity
    if order_item.quantity < 1:
        return False, f"{order_item.item_name}: Quantity must be at least 1."
    if order_item.quantity > 100:
        return False, f"{order_item.item_name}: Quantity must be at most 100."

    # get Adora-specific item id
    adora_item_id_res = get_adora_item_id(
        menu_name_to_id_map,
        order_item.item_name,
        openai_client,
        openai_model,
    )
    if not adora_item_id_res.success:
        return False, adora_item_id_res.message
    adora_item_id = int(adora_item_id_res.message)

    # get Adora-specific item name
    item_details = menu_id_to_details_map.get(adora_item_id)
    if item_details:
        adora_item_name = item_details.name
    else:
        return False, "Failed to get item in the menu."

    # get Adora-specific size id
    adora_size_id_res = get_adora_size_id(
        menu_id_to_details_map,
        size_map,
        adora_item_id,
        order_item.size,
        openai_client,
        openai_model,
    )
    if not adora_size_id_res.success:
        return False, adora_size_id_res.message
    adora_size_id = int(adora_size_id_res.message)

    # get Adora-specific size name
    adora_size_name = size_map.get(adora_size_id)
    if adora_size_name is None:
        return False, "Failed to get size of item in the menu."

    # get Adora-specific modifications and create the AdoraOrderItem
    adora_modifications_res = get_adora_modifications(
        adora_item_name,
        adora_item_id,
        adora_size_name,
        adora_size_id,
        menu_id_to_details_map,
        menu_modifiers,
        menu_modifier_groups,
        openai_client,
        openai_model,
        order_item,
        order_item.modifications,
    )

    return adora_modifications_res
