import textwrap
from dataclasses import dataclass
from decimal import Decimal

from phi.memory.memory import Memory

from agent.memory import delete_memory, get_memory, set_memory_manager
from agent.model import ModelName, get_client
from tools.ordering_tools.classes import (
    Consumer,
    GenericCoupon,
    GenericDeliveryAddress,
    LLMCartInfo,
    LLMFulfillmentStrategy,
    OrderItem,
)
from tools.ordering_tools.integrations.adora._conversion_examples import (
    COUPON_EXAMPLES,
    ITEM_ID_EXAMPLES,
    MODIFIER_EXAMPLES,
    SIZE_EXAMPLES,
)
from tools.ordering_tools.integrations.adora.classes import (
    AdoraCoupon,
    AdoraOrderItem,
    MenuItemDetails,
)
from utils.secret import get_client_secret_with_fallback


@dataclass
class ConversionResult:
    success: bool
    message: str


model_router_client = get_client()
model_router_model = ModelName.MEDIUM


def _add_default_modifiers(
    item_modifier_groups: list, modifier_id_to_group_id: dict
) -> tuple[list, dict]:
    modifiers = []
    modifier_group_counter = {}
    for group in item_modifier_groups:
        group_id = group["modifier_group_id"]
        for modifier in group["modifiers"]:
            if modifier["default"]:
                modifiers.append(
                    {
                        "id": modifier["modifier_id"],
                        "weightId": 3,
                    }
                )
                if group_id not in modifier_group_counter:
                    modifier_group_counter[group_id] = []
                modifier_group_counter[group_id].append(modifier["modifier_id"])
            modifier_id_to_group_id[modifier["modifier_id"]] = group_id
    return modifiers, modifier_group_counter


def convert_address_string(address: str) -> GenericDeliveryAddress | None:
    """Given a delivery address string, parse it into a GenericDeliveryAddress object.

    Args:
        address (str): The address.

    Returns:
        GenericDeliveryAddress | None: The parsed delivery address.
    """
    response = model_router_client.beta.chat.completions.parse(
        model=model_router_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """You are given an address.
                        For the state field, if the user provides an abbreviation, output the full state name.
                        For example, if the user entered "CA", output "California".
                        If any field is missing, output "N/A" for that field.
                        If the user did not provide a delivery address, output "N/A" for all fields.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{address}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=GenericDeliveryAddress,
    )

    return response.choices[0].message.parsed


def convert_coupon(
    all_coupons: list[AdoraCoupon],
    target_coupon: str,
    coupon_conversion_examples: dict[str, str],
) -> ConversionResult:
    """
    Finds the closest coupon name in the list of available coupons and consequent coupon id.
    """
    coupon_name_to_id_map = {c.name: c.id for c in all_coupons}
    coupon_conversion_examples_string = COUPON_EXAMPLES
    if coupon_conversion_examples:
        coupon_conversion_examples_string = textwrap.dedent(
            f"""
            # EXAMPLE #
            EXAMPLE AVAILABLE COUPONS: {[f"{c.name} ({c.description})" for c in all_coupons]}
            """
            + "\n\n".join(
                [
                    f"User: {k}\nAgent: {v}"
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

        {coupon_conversion_examples_string}

        #########

        # RESPONSE FORMAT #
        Only output the most similar coupon name. Output "N/A" if the user's inputted coupon name is nothing like any of the available options.
        """
    )
    response = model_router_client.chat.completions.create(
        model=model_router_model,
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
    if not coupon_name:
        return ConversionResult(
            False, "Failed to get a response from LLM. Please try again."
        )
    if coupon_name in coupon_name_to_id_map:
        return ConversionResult(True, str(coupon_name_to_id_map[coupon_name]))

    return ConversionResult(False, "Coupon not available.")


def get_adora_item_id(
    menu_name_to_id_map: dict,
    order_item_name: str,
    item_id_conversion_examples: dict[str, str],
) -> ConversionResult:
    """
    Finds the closest item name in the menu and consequent item id.
    """
    item_id_conversion_examples_string = ITEM_ID_EXAMPLES
    if item_id_conversion_examples:
        item_id_conversion_examples_string = textwrap.dedent(
            f"""
            # EXAMPLE #
            EXAMPLE MENU: {list(menu_name_to_id_map.keys())[:20] + ["..."]}
            """
            + "\n\n".join(
                [
                    f"User: {k}\nAgent: {v}"
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

        {item_id_conversion_examples_string}

        #########

        # RESPONSE FORMAT #
        Only output the most similar menu item name. Output "N/A" if the user's inputted item name is nothing like any of the available options.
        """
    )
    response = model_router_client.chat.completions.create(
        model=model_router_model,
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


def get_adora_modifications(
    adora_item_name: str,
    adora_item_id: int,
    adora_size_name: str,
    adora_size_id: int,
    menu_id_to_details_map: dict[int, MenuItemDetails],
    menu_modifiers: dict,
    menu_modifier_groups: dict,
    modifier_weights_map: dict,
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
        menu_id_to_details_map (dict): A mapping of item IDs to their details.
        menu_modifiers (dict): The restaurant's menu modifiers.
        menu_modifier_groups (dict): The restaurant's menu modifier groups.
        modifier_weights_map (dict): A mapping of modifier weights to their IDs.
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
        modifier_weights_map,
        modifier_conversion_examples,
    )
    payload["comment"] = comment

    # If there are no modifier groups, create an AdoraOrderItem with no modifications
    if not item_modifier_groups:
        if modifiers:
            return False, "No modifiers are allowed for this item."
        adora_order_item = AdoraOrderItem(
            adora_item_id, adora_size_id, order_item.quantity, comment, Decimal(0.0), []
        )
        adora_order_item.item_name = adora_item_name
        adora_order_item.size = adora_size_name
        adora_order_item.quantity = order_item.quantity
        adora_order_item.modifications = []
        return True, adora_order_item

    # Add all default modifiers and track modifier group constraints
    modifier_id_to_group_id = {}
    default_modifiers, modifier_group_counter = _add_default_modifiers(
        item_modifier_groups, modifier_id_to_group_id
    )
    payload["modifiers"].extend(default_modifiers)

    # Add user-provided modifiers to payload and update group counts
    new_added_modifications: list[str] = []
    modifier_lookup = {modifier["id"]: modifier for modifier in payload["modifiers"]}
    process_added_modifiers(
        modifier_group_counter,
        modifier_id_to_group_id,
        modifier_lookup,
        modifiers,
        new_added_modifications,
        payload,
    )

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
        Decimal(0.0),
        payload["modifiers"],
    )

    adora_order_item.item_name = adora_item_name
    adora_order_item.size = adora_size_name
    adora_order_item.quantity = order_item.quantity
    adora_order_item.modifications = new_added_modifications
    return True, adora_order_item


def get_adora_secret(account_name: str, secret_type: str) -> str:
    """
    Retrieve the Adora secret (API key or secret) for the given account_name.
    First tries Secrets Manager, falls back to environment variable if an error occurs.

    Args:
        account_name (str): The account name for which to retrieve the secret.
        secret_type (str): The type of secret (e.g., "ADORA_API_KEY" or "ADORA_API_SECRET").

    Returns:
        str: The retrieved secret value.
    """
    secret_key = f"{account_name.upper()}_ADORA_{secret_type}"
    secret_value = get_client_secret_with_fallback(secret_key)
    return secret_value


def get_adora_size_id(
    menu_id_to_details_map: dict[int, MenuItemDetails],
    size_map: dict[int, str],
    adora_item_id: int,
    order_item_size: str,
    size_id_conversion_examples: dict[str, str],
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
        # If no size was supplied but multiple size options are available for item -> error
        if not order_item_size:
            return ConversionResult(
                False,
                f"Please provide a size for the item. Available size options: {size_options}",
            )

        size_id_conversion_examples_string = SIZE_EXAMPLES
        if size_id_conversion_examples:
            size_id_conversion_examples_string = textwrap.dedent(
                f"""
                # EXAMPLE #
                EXAMPLE AVAILABLE SIZE OPTIONS: {size_options}
                """
                + "\n\n".join(
                    [
                        f"User: {k}\nAgent: {v}"
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

            {size_id_conversion_examples_string}

            #########

            # RESPONSE FORMAT #
            Only output the most similar item size. Output "N/A" if the user's inputted item size is nothing like any of the available options.
            """
        )
        response = model_router_client.chat.completions.create(
            model=model_router_model,
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
        if not item_size:
            return ConversionResult(
                False, "Failed to get a response from LLM. Please try again."
            )
        size_id = size_options.get(item_size)
        if size_id:
            return ConversionResult(True, str(size_id))

        # Get all the keys as a list
        size_options = list(size_options.keys())

        return ConversionResult(
            False, f"Size not found in menu, the options are {size_options}"
        )


def get_cart_info(
    chat_history: list[str], cart_conversion_sys_prompt: str
) -> LLMCartInfo | None:
    """Extracts the cart information from the chat history.

    Args:
        chat_history (str): The chat history to extract the cart information from.
        cart_conversion_sys_prompt (str): A system prompt to help the model understand the context of the chat history.

    Returns:
        LLMCartInfo | None: The parsed cart information.
    """
    response = model_router_client.beta.chat.completions.parse(
        model=model_router_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Your role is to process the chat history between a user and an agent. "
                            + "You will extract the relevant order information into the desired format. "
                            + "You will be provided with the chat history to process. "
                            + "If agent messages exist, prioritize agent messages over user messages because agent messages contain more precise order item information. "
                            + (
                                f"\nAdditional Instructions: {cart_conversion_sys_prompt}"
                                if cart_conversion_sys_prompt
                                else ""
                            )
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=LLMCartInfo,
    )

    return response.choices[0].message.parsed


def get_consumer_info(chat_history: list[str], memory_list: str) -> Consumer | None:
    """Extracts the consumer information from the chat history.

    Args:
        chat_history (str): The chat history to extract the consumer information from.
        memory_list (str): The list of memories to extract the consumer information from.

    Returns:
        Consumer | None: The parsed consumer information.
    """
    response = model_router_client.beta.chat.completions.parse(
        model=model_router_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an agent.
                        You will extract the relevant customer information into the desired format.
                        You will be provided with the chat history to process.
                        The phone number, if provided, MUST be a 10-digit number and can be in any format.
                        Extract the phone number as a string of exactly 10 digits without any formatting.
                        If the customer information is not present, output "N/A" for the missing fields.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{chat_history}"},
                    {"type": "text", "text": f"{memory_list}"},
                ],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=Consumer,
    )

    return response.choices[0].message.parsed


def get_consumer_memory(account_name: str, user_id: str) -> list[Memory] | None:
    """Get the list of memories for the given account name.

    Args:
        account_name (str): The account name to get the memory for.

    Returns:
        list[Memory] | None: The list of memories object.
    """
    memory = get_memory(account_name)
    memory.user_id = user_id
    memory.load_user_memories()
    memories = memory.memories
    return memories


def add_order_to_memory(account_name: str, user_id: str, order_details: str) -> None:
    """Add the consumer memory for the given account name.

    Args:
        account_name (str): The account name to add the memory for.
        user_id (str): The user ID to add the memory for.
        order_details (str): The order details to add to the memory.

    Returns:
        None
    """
    order_details = "User's previous order details: " + order_details
    memory = get_memory(account_name)
    memory.user_id = user_id
    set_memory_manager(memory, user_id)
    memory.load_user_memories()
    order_memories = []
    memories = memory.memories
    # Get the oldest order memory
    if memories:
        order_memories = [
            memo
            for memo in memories
            if memo.memory.startswith("User's previous order details:")
        ]
    # If there are more than 2 order memories, delete the oldest one
    if memory.manager and len(order_memories) >= 2:
        oldest_order_memory = order_memories[1]
        delete_memory(memory, oldest_order_memory)
    if memory.manager:
        memory.manager.add_memory(order_details)


def get_delivery_address(
    chat_history: list[str], memory_list: str
) -> GenericDeliveryAddress | None:
    """Extracts the delivery address from the chat history.

    Args:
        chat_history (str): The chat history to extract the delivery address from.

    Returns:
        GenericDeliveryAddress | None: The parsed delivery address. If no delivery address is found, return "N/A".
    """
    response = model_router_client.beta.chat.completions.parse(
        model=model_router_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an agent.
                        You will be provided with the chat history to process.
                        You will extract the relevant delivery address information.
                        For the state field, if the user provides an abbreviation, output the full state name.
                        For example, if the user entered "CA", output "California".
                        If any field is missing, output "N/A" for that field.
                        If the user did not provide a delivery address, output "N/A" for all fields.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{chat_history}"},
                    {"type": "text", "text": f"{memory_list}"},
                ],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=GenericDeliveryAddress,
    )

    return response.choices[0].message.parsed


def get_fulfillment_strategy(chat_history: list[str]) -> LLMFulfillmentStrategy | None:
    """Extracts the fulfillment strategy from the chat history.

    Args:
        chat_history (str): The chat history to extract the fulfillment strategy from.

    Returns:
        LLMFulfillmentStrategy | None: The parsed fulfillment strategy. If no fulfillment strategy is found, return "N/A".
    """
    response = model_router_client.beta.chat.completions.parse(
        model=model_router_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an agent.
                        You will be provided with the chat history to process.
                        You will extract the relevant fulfillment strategy.
                        DO NOT extract the strategy from the infomation under ## Existing Memories.
                        The possible options are "delivery", "pickup" or "N/A" if no strategy is specified.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=LLMFulfillmentStrategy,
    )

    return response.choices[0].message.parsed


def get_generic_coupon_info(chat_history: list[str]) -> GenericCoupon | None:
    """Extracts the coupon information from the chat history.

    Args:
        chat_history (str): The chat history to extract the coupon information from.

    Returns:
        GenericCoupon | None: The parsed coupon information. If no coupon information is found, return "N/A".
    """
    response = model_router_client.beta.chat.completions.parse(
        model=model_router_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an agent.
                        You will be provided with the chat history to process.
                        You will extract the relevant coupon information, if the user used a coupon.
                        A user can only use one coupon per order, so extract the most recent coupon used.
                        If there is no coupon used, output "N/A" in the coupon field.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=GenericCoupon,
    )

    return response.choices[0].message.parsed


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


def get_modifier_weights_map(menu) -> dict[str, int]:
    """
    Extracts the modifier weight map from the menu data.

    Args:
        menu (dict): The menu data containing the modifier weights.

    Returns:
        dict: A dictionary mapping modifier weight names to their corresponding IDs.
    """

    return {
        weight["name"]: weight["modifier_weight_id"]
        for weight in menu["modifier_weights"]
    }


def get_similar_modifier_using_openai(
    order_item_modification: str,
    modifier_names: list,
    modifier_weights_map: dict[str, int],
    modifier_conversion_examples: dict[str, str],
) -> str | None:
    """
    Uses OpenAI's language model to match a user-supplied item modification to the most similar modifier on the menu.

    Args:
        order_item_modification (str): The user-provided modification for an order item (e.g., "extra cheese").
        modifier_names (list): A list of available modifier names on the menu.
        modifier_weights_map (dict): A mapping of modifier weights to their IDs.

    Returns:
        str: The most similar modifier from the menu or "N/A" if no close match is found.
    """

    modifier_conversion_examples_string = MODIFIER_EXAMPLES
    if modifier_conversion_examples:
        modifier_conversion_examples_string = textwrap.dedent(
            f"""
            # EXAMPLE #
            EXAMPLE AVAILABLE MODIFICATION OPTIONS: {modifier_names}
            EXAMPLE AVAILABLE MODIFICATION WEIGHTS OPTIONS: {modifier_weights_map}
            """
            + "\n\n".join(
                [
                    f"User: {k}\nAgent: {v}"
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
        Here are the AVAILABLE MODIFICATION WEIGHTS OPTIONS: {modifier_weights_map}

        #########

        # OBJECTIVE #
        Match the user's inputted item modification with the weight to the closest item modification on the menu as if you were a server/waiter.
        If there is a conflict between the name and the weight , prioritize the name over the weight (e.g., "extra cheese"), otherwise prioritize the weight ("extra sausage").
        If there is no weight provided, default to "Regular."
        Treat words like "extra," "light," or "none" as descriptors for the weight only if they are not part of the actual modifier name.

        #########

        {modifier_conversion_examples_string}

        #########


        # RESPONSE FORMAT #
        Only output the most similar item modification. Output "N/A" if the user's inputted item modification is nothing like any of the available options.
        The output should always be in the format: "<Modifier Name>(<Weight>)"
        """
    )
    response = model_router_client.chat.completions.create(
        model=model_router_model,
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


def convert_to_adora_item(generic_cart) -> dict[str, AdoraOrderItem] | None:
    """Parses the string-based cart from an LLM's structured output field into an array of objects.

    Args:
        generic_cart (dict): A dictionary containing the cart items with required details for AdoraItem.

    Returns:
        dict[str, AdoraOrderItem] | None: The parsed cart items as AdoraOrderItem objects.

    """
    if not generic_cart:
        return None
    cart = {}
    for item in generic_cart:
        order_item = AdoraOrderItem(
            int(item["itemId"]),
            int(item["sizeId"]),
            int(item["quantity"]),
            item.get("comment", ""),
            Decimal(item["price"]),
            item["modifiers"],
        )
        cart[item["itemName"]] = order_item
    return cart


def process_modifiers(
    menu_modifiers: dict,
    order_item_modifications: list,
    modifier_weights_map: dict[str, int],
    modifier_conversion_examples: dict[str, str],
) -> tuple[list, str]:
    """
    Processes user-supplied order item modifications, classifying them as valid modifiers or comments.

    Args:
        menu (dict): The restaurant's menu data, containing items and modifiers.
        modifier_weights_map (dict): A mapping of modifier weights to their IDs.
        order_item_modifications (list): A list of modifications provided by the user for a specific order item.

    Returns:
        tuple[list, str]:
            - A list of valid modifier IDs matched to the menu modifiers.
            - A comment string containing the user-provided modifications that did not match any menu modifiers.
    """
    modifier_names = [modifier["name"] for modifier in menu_modifiers]
    modifiers = []
    comment = ""

    for order_item_modification in order_item_modifications:
        matched_modifier_with_weight = get_similar_modifier_using_openai(
            order_item_modification,
            modifier_names,
            modifier_weights_map,
            modifier_conversion_examples,
        )

        # Split into parts
        if matched_modifier_with_weight:
            matched_modifier, weights = matched_modifier_with_weight.split("(")
        else:
            matched_modifier, weights = "N/A", "N/A"

        # Clean up the weight part by removing the closing parenthesis
        weights = weights.rstrip(")")

        most_similar_modifier_id = next(
            (
                modifier["modifier_id"]
                for modifier in menu_modifiers
                if modifier["name"] == matched_modifier
            ),
            None,
        )

        if most_similar_modifier_id:
            modifiers.append(
                {
                    "id": most_similar_modifier_id,
                    "name": matched_modifier,
                    "weightId": modifier_weights_map[weights],
                }
            )
        else:
            comment += order_item_modification + ". "

    return modifiers, comment


def process_added_modifiers(
    modifier_group_counter: dict,
    modifier_id_to_group_id: dict,
    modifier_lookup: dict,
    modifiers: list[dict],
    new_added_modifications: list[str],
    payload: dict,
):
    """
    Processes user-provided modifiers, updating existing modifiers in payload or appending new ones.
    Args:
        modifier_group_counter (dict): Counter for modifier group constraints.
        modifier_id_to_group_id (dict): Mapping of modifier IDs to their group IDs.
        modifier_lookup (dict): Lookup dictionary for existing modifiers by ID.
        modifiers (list[dict]): List of user-provided modifiers.
        new_added_modifications (list[str]): List to store names of newly added modifications.
        payload (dict): The payload containing existing modifiers and comment.

    Returns:
        None: Modifies the payload, modifier_lookup, and counters in-place.
    """
    for modifier_item in modifiers:
        if modifier_item["id"] in modifier_lookup:
            # if the modifier is already in the payload, update the weight
            existing_modifier = modifier_lookup[modifier_item["id"]]

            # Update the existing modifier with the new weight
            existing_modifier.update(
                {
                    "id": modifier_item["id"],
                    "weightId": modifier_item["weightId"],
                }
            )
        elif modifier_item["weightId"] == 1:
            # if the modifier is not in the payload and the weight is "NONE", skip
            continue
        else:
            # Add the new modifier and update the lookup
            new_modifier = {
                "id": modifier_item["id"],
                "weightId": modifier_item["weightId"],
            }
            payload["modifiers"].append(new_modifier)
            modifier_lookup[modifier_item["id"]] = new_modifier

        if modifier_item["id"] in modifier_id_to_group_id:
            if (
                modifier_id_to_group_id[modifier_item["id"]]
                not in modifier_group_counter
            ):
                modifier_group_counter[modifier_id_to_group_id[modifier_item["id"]]] = (
                    []
                )
            modifier_group_counter[modifier_id_to_group_id[modifier_item["id"]]].append(
                modifier_item["id"]
            )
        new_added_modifications.append(modifier_item["name"])


def validate_and_convert_item(
    order_item: OrderItem,
    menu_maps: tuple[dict[int, MenuItemDetails], dict[str, int]],
    modifier_weights_map: dict[str, int],
    size_map: dict[int, str],
    menu_modifiers: dict,
    menu_modifier_groups: dict,
    item_id_conversion_examples: dict[str, str],
    size_id_conversion_examples: dict[str, str],
    modifier_conversion_examples: dict[str, str],
) -> tuple[bool, AdoraOrderItem | str]:
    """Converts a generic order item into an Adora order item.

    Args:
        order_item (OrderItem): The generic order item to convert.
        menu_maps (tuple): A tuple containing the menu ID to details map and name to ID map.
        size_map (dict[int, str]): Mapping of size IDs to size descriptions.
        menu_modifiers (dict): The menu modifiers.
        menu_modifier_groups (dict): The menu modifier groups.
        item_id_conversion_examples (dict[str, str]): Dictionary of conversion examples for item IDs.
        size_id_conversion_examples (dict[str, str]): Dictionary of conversion examples for size IDs.
        modifier_conversion_examples (dict[str, str]): Dictionary of conversion examples for modifiers.

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
    )
    if not adora_item_id_res.success:
        return False, adora_item_id_res.message
    adora_item_id = int(adora_item_id_res.message)

    # get Adora-specific item name
    item_details = menu_id_to_details_map.get(adora_item_id)
    if item_details:
        adora_item_name = item_details.name
    else:
        return (
            False,
            f"Failed to get item details for item ID {adora_item_id} in the menu.",
        )

    # get Adora-specific size id
    adora_size_id_res = get_adora_size_id(
        menu_id_to_details_map,
        size_map,
        adora_item_id,
        order_item.size,
        size_id_conversion_examples,
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
        modifier_weights_map,
        order_item,
        modifier_conversion_examples,
    )

    return adora_order_item_conversion_res


def validate_modifier_group_constraints(
    modifier_group_counter: dict,
    menu_modifier_groups: dict,
    payload: dict,
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
    DEFAULT_MODIFIER_COUNT = 2
    DEFAULT_MODIFIER_MAX_COUNT = 1

    modifier_group_dict = {mg["modifier_group_id"]: mg for mg in menu_modifier_groups}

    for modifier_group_id, modifiers in modifier_group_counter.items():
        count = len(modifiers)
        if modifier_group_id in modifier_group_dict:
            mg = modifier_group_dict[modifier_group_id]
            if count < mg["min_required_modifier"]:
                return (
                    False,
                    f"Please provide at least {mg['min_required_modifier']} modifiers for {mg['name']}.",
                )
            if count > mg["max_allowed_modifier"]:
                # limit to 2 modifiers for default modifier
                if (
                    mg["max_allowed_modifier"] == DEFAULT_MODIFIER_MAX_COUNT
                    and count == DEFAULT_MODIFIER_COUNT
                ):
                    # remove the first modifier
                    default_modifier, _ = modifiers
                    payload["modifiers"] = [
                        mod
                        for mod in payload["modifiers"]
                        if mod["id"] != default_modifier
                    ]
                    return True, ""
                return (
                    False,
                    f"Please provide at most {mg['max_allowed_modifier']} modifiers for {mg['name']}.",
                )

    return True, ""
