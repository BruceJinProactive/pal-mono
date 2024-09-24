from dataclasses import dataclass


@dataclass
class ConversionResult:
    success: bool
    message: str


def get_adora_item_id(
    menu, order_item_name: str, openai_client, openai_model: str
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


def get_adora_size_id(
    menu, adora_item_id: int, order_item_size: str, openai_client, openai_model: str
) -> ConversionResult:
    """
    Maps the size to size id.
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
    for size_id, size in size_descriptions.items():
        if size == item_size:
            return ConversionResult(True, size_id)

    return ConversionResult(False, "Size not found in menu.")
