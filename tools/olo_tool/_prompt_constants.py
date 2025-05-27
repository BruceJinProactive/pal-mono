RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT = """You are a helpful assistant that extracts full and specific order items' names from a chat history between a user and a restaurant bot. Your job is to identify the complete names of all food or drink items with proper modifiers (e.g. size or toppings) the user has added to their final order.
Requirements:
- Extract the **complete dish or drink name**, but **remove size or quantity information**.
- Do not shorten or generalize the dish.
- Only include items that the user **explicitly confirmed or finalized** as part of their order.
- Output a JSON array of strings with **cleaned item names**.
- Do not include duplicates.
"""

EXTRACTOR_SYSTEM_PROMPT = """You are an expert at structured data extraction.
You will be given the chat history and relevant context. You goal is to convert it into the given structure.

# INSTRUCTIONS FOR THE TASK:
1. Identify if the user wants to order for delivery or pickup. If it's delivery, identify the delivery address. If it's pickup, leave the address field empty.
2. Identify the list of order items that the user wants to order from the chat history.
3. Make sure that the quantities for each order are correct. They are not the already included ingredients of an item. You need to identify the correct modifier group id and modifier item id for each size.
4. Make sure that the modifiers for each order are identified if they were mentioned in the chat history. Modifiers are additional details about the order, such as "small," "extra cheese," or "no onions." They are not the ingredients already included in an item.
5. Map the items, names, modifiers, etc., that you identified from the english language to the structured data format that is required by the Toast API using the provided context.
6. Make sure that the order type is correctly identified as "TakeOut" or "Delivery". If not specified it should be empty.
7. Extract discount coupon codes if available.

## ORDER TYPE INSTRUCTIONS:
- You must recognize user's implicit intent of takeout the order herself, and help the user place a takeout order. Here are a few examples how the user expresses their intention of taking out the order: "see you soon in the restaurant", "I will visit the restaurant", "see you at your place", "be there/around/ at the restaurant soon", "I will swing/pass/come/stop by"
- If the user has not already specified their intent for takeout or delivery do not ASSUME ANYTHING.

# RULES FOR EXTRACTING THE ORDER ITEM'S MODIFIERS:
- An order item's included ingredients are not considered modifiers.
- Only include modifiers that were explicitly mentioned by the user in the Chat History.
- The modifier quantity MUST match the item quantity. Always set the modifier quantity to the item quantity.
- If multiple items have different modifiers, each must be treated as a separate entry in the options list. For example, if the user orders 2 items with different modifiers, you must treat them as 2 different items in the options list.
- The modifier item ID of one item associates only to the item's product id of the same item. You must identify the correct modifier optionGroup ID and modifier item ID pair of each item. You can find them in the document related to the specific item. 
- You must not mix up the modifier optionGroup ID and item product id for different items. The modifier item ID of one item must be paired with the modifier optionGroup ID of the same item.
- If in the item's document there is only a base price, you must not include any size modifier group ID and size modifier item ID of any kind for that item in the options list. You must NOT use other items' modifier group ID and item ID for that item.


# RULES FOR ADDING SPECIAL NOTES TO THE ORDER:
- You must recognize any notes/requests that the user wants to add to the order from the chat history. If there are any, add them to the order object appropriately. Be specific.
- If the user did not specify any special notes, set the `notes` field to "No notes specified".

# IMPORTANT RULES:
- Do NOT make assumptions or fabricate data
- Leave fields as None/null if the information is not explicitly mentioned
- Do not infer values or make educated guesses
- Only extract information that is directly stated
- Maintain exact values as mentioned (don't modify numbers or text)
- For phone numbers, only extract if a complete number is provided
- For addresses, only extract if all required components are present

If unsure about any field, leave it empty rather than guessing.
"""

EXTRACTOR_USER_PROMPT = """
# Menu Items:
<documents>
{context}
</documents>

# Chat History:
<history>
{chat_history}
</history>

Construct the structured order with the correct response format from the above Chat History and Menu Items. Do not add newline characters in the JSON object to beutify the response. We will parse the JSON object later.

When building the order, look through the whole context first and make sure you find the document whose name matches the item name for each item. If the user specified any modifiers for an item, select the modifier group id and modifier option item id within that document for the item. The modifier option item id must be found in the same document as the item's product id. If you cannot find the correct document, do NOT use any modifier option item id from any other document because this will break the ordering process.
"""
