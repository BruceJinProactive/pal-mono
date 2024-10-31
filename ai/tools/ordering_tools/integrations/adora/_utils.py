import textwrap
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
    all_coupons: list[AdoraCoupon],
    target_coupon: str,
    openai_client,
    openai_model: str,
    coupon_conversion_examples: dict[str, str],
) -> ConversionResult:
    """
    Finds the closest coupon name in the list of available coupons and consequent coupon id.
    """
    coupon_name_to_id_map = {c.name: c.id for c in all_coupons}
    coupon_conversion_examples_string = textwrap.dedent(
        """
        # EXAMPLE #
        EXAMPLE AVAILABLE COUPONS: ["$5 Off", "20% off", "Free Bagel with Purchase of Coffee"]

        User: five bucks off
        Assistant: $5 Off

        User: twenty percent reduced
        Assistant: 20% off
        
        User: free bagel coupon
        Assistant: Free Bagel with Purchase of Coffee

        User: $10 Off
        Assistant: N/A

        User: 30% off
        Assistant: N/A
        
        User: free sandwich
        Assistant: N/A
        """
    )
    if coupon_conversion_examples:
        coupon_conversion_examples_string = textwrap.dedent(
            f"""
            # EXAMPLE #
            EXAMPLE AVAILABLE COUPONS: {[f"{c.name} ({c.description})" for c in all_coupons]}
            
            """
            + "\n\n".join(
                [
                    f"User: {k}\nAssistant: {v}"
                    for k, v in coupon_conversion_examples.items()
                ]
            )
        )

    # Get GPT to find the most similar item name
    sys_prompt = textwrap.dedent(
        f"""
        # CONTEXT #
        I am a waiter at a restaurant. I am taking a user's order. 
        I want to match a user supplied coupon name to a coupon in the available coupons list. 
        Here are the AVAILABLE COUPONS: {list(coupon_name_to_id_map.keys())}
        Here are the AVAILABLE COUPONS along with a helpful description: {[f"{c.name} ({c.description})" for c in all_coupons]}

        #########

        # OBJECTIVE #
        Match the user's inputted coupon name to the closest coupon option in the list of available coupons as if you were a server/waiter.

        #########

        """
        + coupon_conversion_examples_string
        + """

        #########

        # RESPONSE FORMAT #
        Only output the most similar coupon name. Output "N/A" if the user's inputted coupon name is nothing like any of the available options.
        """
    )
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
                    {"type": "text", "text": target_coupon},
                ],
            },
        ],
        temperature=0,
        max_tokens=256,
        response_format={"type": "text"},
    )

    coupon_name = response.choices[0].message.content
    if coupon_name in coupon_name_to_id_map:
        return ConversionResult(True, str(coupon_name_to_id_map[coupon_name]))

    return ConversionResult(False, "Coupon not available.")


def get_adora_item_id(
    menu_name_to_id_map: dict,
    order_item_name: str,
    item_id_conversion_examples: dict[str, str],
    openai_client,
    openai_model: str,
) -> ConversionResult:
    """
    Finds the closest item name in the menu and consequent item id.
    """
    item_id_conversion_examples_string = textwrap.dedent(
        """
        # EXAMPLE #
        EXAMPLE MENU: ["Coke", "Sprite"]

        User: coke
        Assistant: Coke

        User: spritw
        Assistant: Sprite

        User: pepsi
        Assistant: N/A

        User: coke zero
        Assistant: N/A
        """
    )
    if item_id_conversion_examples:
        item_id_conversion_examples_string = textwrap.dedent(
            f"""
            # EXAMPLE #
            EXAMPLE MENU: {list(menu_name_to_id_map.keys())[:20] + ["..."]}
            
            """
            + "\n\n".join(
                [
                    f"User: {k}\nAssistant: {v}"
                    for k, v in item_id_conversion_examples.items()
                ]
            )
        )

    # Get GPT to find the most similar item name
    sys_prompt = textwrap.dedent(
        f"""
        # CONTEXT #
        I am a waiter at a restaurant. I am taking a user's order. 
        I want to match a user supplied item name to an item on the menu. 
        Here is the MENU: {list(menu_name_to_id_map.keys())}

        #########

        # OBJECTIVE #
        Match the user's inputted item name to the closest item option on the menu as if you were a server/waiter.

        #########

        """
        + item_id_conversion_examples_string
        + """

        #########

        # RESPONSE FORMAT #
        Only output the most similar menu item name. Output "N/A" if the user's inputted item name is nothing like any of the available options.
        """
    )
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

    return ConversionResult(False, f"Item {order_item_name} not found in menu.")


def get_adora_size_id(
    menu_id_to_details_map: dict[int, MenuItemDetails],
    size_map: dict[int, str],
    adora_item_id: int,
    order_item_size: str,
    size_id_conversion_examples: dict[str, str],
    openai_client,
    openai_model: str,
) -> ConversionResult:
    """
    Maps the size to size id.
    """
    # Find available size ids for the item
    available_sizes: set = set()
    if adora_item_id in menu_id_to_details_map:
        for size in menu_id_to_details_map[adora_item_id].order_types[0]["sizes"]:
            available_sizes.add(size["size_id"])

    # Available sizes for the item
    # example: {'12"': 1, '14"': 2, '18"': 3, 'Gluten Free 12"': 4}
    size_options = {size_map[size]: size for size in available_sizes}

    if len(size_options) == 0:
        return ConversionResult(False, "No sizes found for the item.")
    # Only 1 size option, so return the size id directly and skip LLM
    elif len(size_options) == 1:
        # get the value from the only key in the dictionary
        key = next(iter(size_options))
        size_id = size_options[key]
        return ConversionResult(True, str(size_id))
    else:
        size_id_conversion_examples_string = textwrap.dedent(
            """
            # EXAMPLE #
            EXAMPLE AVAILABLE SIZE OPTIONS: ["Small", "Medium", "Large", "Size 5", "Size 6", "Size 7"]

            User: large
            Assistant: Large

            User: Size5
            Assistant: Size 5

            User: Size 8
            Assistant: N/A

            User: size 4
            Assistant: N/A

            User: extra large
            Assistant: N/A
            """
        )
        if size_id_conversion_examples:
            size_id_conversion_examples_string = textwrap.dedent(
                f"""
                # EXAMPLE #
                EXAMPLE AVAILABLE SIZE OPTIONS: {size_options}
                
                """
                + "\n\n".join(
                    [
                        f"User: {k}\nAssistant: {v}"
                        for k, v in size_id_conversion_examples.items()
                    ]
                )
            )

        sys_prompt = textwrap.dedent(
            f"""
            # CONTEXT #
            I am a waiter at a restaurant. I am taking a user's order.
            I want to match a user supplied item size to an available item size on the menu.
            Here are the AVAILABLE SIZE OPTIONS: {size_options}

            #########

            # OBJECTIVE #
            Match the user's inputted item size to the closest item size on the menu as if you were a server/waiter.

            #########

            """
            + size_id_conversion_examples_string
            + """

            #########

            # RESPONSE FORMAT #
            Only output the most similar item size. Output "N/A" if the user's inputted item size is nothing like any of the available options.
            """
        )
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
        size_id = size_options.get(item_size)
        if size_id:
            return ConversionResult(True, str(size_id))

        # Get all the keys as a list
        size_options = list(size_options.keys())

        return ConversionResult(
            False, f"Size not found in menu, the options are {size_options}"
        )


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
    modifier_conversion_examples: dict[str, str],
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

    modifier_conversion_examples_string = textwrap.dedent(
        """
        # EXAMPLE #
        EXAMPLE AVAILABLE MODIFICATION OPTIONS: ["Rainbow Sprinkles", "Gummy Bears", "Whipped Cream", "Peanuts"]
        User: rainbow sprinkles
        Assistant: Rainbow Sprinkles

        User: pnuts
        Assistant: peanuts

        User: nutella
        Assistant: N/A

        User: cherries
        Assistant: N/A
        """
    )
    if modifier_conversion_examples:
        modifier_conversion_examples_string = textwrap.dedent(
            f"""
            # EXAMPLE #
            EXAMPLE AVAILABLE MODIFICATION OPTIONS: {modifier_names}
            
            """
            + "\n\n".join(
                [
                    f"User: {k}\nAssistant: {v}"
                    for k, v in modifier_conversion_examples.items()
                ]
            )
        )

    sys_prompt = textwrap.dedent(
        f"""
        # CONTEXT #
        I am a waiter at a restaurant. I am taking a user's order.
        I want to match a user supplied item modification to an available item modification on the menu.
        Here are the AVAILABLE MODIFICATION OPTIONS: {modifier_names}

        #########

        # OBJECTIVE #
        Match the user's inputted item modification to the closest item modification on the menu as if you were a server/waiter.

        #########

        """
        + modifier_conversion_examples_string
        + """

        #########


        # RESPONSE FORMAT #
        Only output the most similar item modification. Output "N/A" if the user's inputted item modification is nothing like any of the available options.
        """
    )
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
    modifier_conversion_examples: dict[str, str],
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
            openai_client,
            openai_model,
            order_item_modification,
            modifier_names,
            modifier_conversion_examples,
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
            modifiers.append({"id": most_similar_modifier_id, "name": matched_modifier})
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
    modifier_conversion_examples: dict[str, str],
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

    # Process order item modifications using OpenAI
    modifiers, comment = process_modifiers(
        menu_modifiers,
        order_item.modifications,
        openai_client,
        openai_model,
        modifier_conversion_examples,
    )
    payload["comment"] = comment

    # If there are no modifier groups, create an AdoraOrderItem with no modifications
    if not item_modifier_groups:
        if modifiers:
            return False, "No modifiers are allowed for this item."
        adora_order_item = AdoraOrderItem(
            adora_item_id, adora_size_id, order_item.quantity, comment, 0, []
        )
        adora_order_item.item_name = adora_item_name
        adora_order_item.size = adora_size_name
        adora_order_item.quantity = order_item.quantity
        adora_order_item.modifications = []
        return True, adora_order_item

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
    new_added_modifications: list[str] = []
    for modifier_item in modifiers:
        payload["modifiers"].append(
            {
                "id": modifier_item["id"],
                "isDefault": False,
                "price": 1,  # adjust the price as needed
                "weightId": 3,  # adjust the weightId as needed
            }
        )
        if modifier_item["id"] in modifier_id_to_group_id:
            modifier_group_counter[modifier_id_to_group_id[modifier_item["id"]]] += 1
        new_added_modifications.append(modifier_item["name"])

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
    adora_order_item.modifications = new_added_modifications

    return True, adora_order_item


def validate_and_convert_item(
    order_item: OrderItem,
    menu_maps: tuple[dict[int, MenuItemDetails], dict[str, int]],
    size_map: dict[int, str],
    menu_modifiers: dict,
    menu_modifier_groups: dict,
    item_id_conversion_examples: dict[str, str],
    size_id_conversion_examples: dict[str, str],
    modifier_conversion_examples: dict[str, str],
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
        item_id_conversion_examples,
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
        size_id_conversion_examples,
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

    # get Adora-specific modifications and create the AdoraOrderItem:
    #   (True, AdoraOrderItem) or 'Error message'
    adora_order_item_conversion_res = get_adora_modifications(
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
        modifier_conversion_examples,
    )

    return adora_order_item_conversion_res
