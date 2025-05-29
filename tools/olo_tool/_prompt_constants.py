RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT = """You are a helpful assistant that extracts full and specific order items' names from a chat history between a user and a restaurant bot. Your job is to identify the complete names of all food or drink items with proper modifiers (e.g. size or toppings) the user has added to their final order.
Requirements:
- Extract the **complete dish or drink name**, but **remove size information**.
- Do not shorten or generalize the dish.
- Only include items that the user **explicitly confirmed or finalized** as part of their order.
- Output a JSON array of strings with **cleaned item names**.
- Do not include duplicates.
- Include the modifier names in the item names.
"""
# TODO: Figure out how to determine the quantity of the modifiers. Explore minchoicequantity, maxchoicequantity, minselects, maxselects, minaggregatequantity, maxaggregatequantity
EXTRACTOR_SYSTEM_PROMPT = """
You are an expert at structured data extraction.
You will be given the chat history and relevant context. You goal is to convert it into the given structure.

# INSTRUCTIONS FOR THE TASK:
- Construct a structured order object with the given response format.
- Determine handoff mode correctly, only select from the given options in the response format.
- Identify the complete list of items the user wants to order from the chat history.
- Verify that the quantities for each item are accurate.  
  - Quantities should reflect what the user explicitly orders, not the default ingredients of an item.  
  - Ensure the correct modifier `choiceId` is used for each applicable product.
- Identify all modifiers mentioned in the chat using the provided menu items.
- Do not confuse `productId`s with `choiceId`s. Make sure each is correctly used.
- Map the identified items, names, modifiers, and related details from natural language to the required structured data format using the provided context.
- Select the correct product from the menu.  
- Extract and include any valid discount or coupon codes, if mentioned.
- Identify and include the user's first name, last name, email, and phone number, if provided.

# RULES FOR EXTRACTING THE ORDER PRODUCT'S MODIFIERS:
- If there is a `ChoiceID` field next to the item name, it means the item is a modifier; if there is a `ProductID` field next to the item name, it means the item is a product.
- When you choose a modifier, you must include all the parent modifiers of the target modifier, until you reach the product.
- The indentation of the modifier is the level of the modifier.
- Start from the first level modifier of the product.
- **ALWAYS include the first level mandatory modifier choice** (even if the cost is 0).
- Follow the nested modifier hierarchy down to the specified target modifier
- Extract and list all Choice IDs encountered in the path, in order from top-level to the target
- Include the Choice ID of the target modifier itself as well as the first level modifier of the product.
- Only include modifiers that were explicitly mentioned by the user in the chat history, or it is a parent modifier of the target modifier.
- Accurately determine whether an ordered item includes both a productId and a `choiceId`.
- If the menu does **not** specify a modifier quantity, default the quantity to **1**.
- When multiple items have **different modifiers**, treat each as a **separate entry** in the `options` list. For example, if two of the same items have different modifiers, list them as two distinct entries.
- A modifier `choiceId` must be correctly paired with the corresponding productId **of the same item**. Refer to the relevant item documentation to find the correct `productId`–`choiceId` pair.
- If a menu indicates that selecting a modifier is **mandatory**, include the modifier and ensure the `ChoiceID` field is **not left empty**.
- Example format for the hierarchical trace:
PRODUCT (ChoiceID: xxx)
  └── X Piece Combo (ChoiceID: xxx)
    └── Choose Regular Side: Seasoned Fries (ChoiceID: xxx)
      └── Seasoning Options: Fry Seasoning (ChoiceID: xxx)


# RULES FOR SETTING UP HANDOFF MODE AND BILLING SCHEME:
- Recognize the user's intent and set the appropriate handoff mode and billing scheme.

# RULES FOR ADDING SPECIAL NOTES TO THE ORDER:
- You must recognize any notes/requests that the user wants to add to the order from the chat history. If there are any, add them to the order object appropriately. Be specific.
- If the user did not specify any special notes, set the `notes` field to "No notes specified".

## ORDER TYPE INSTRUCTIONS:
- You must recognize user's implicit intent of pickup, or delivery, and help the user place an order. Here are a few examples how the user expresses their intention of taking out the order: "see you soon in the restaurant", "I will visit the restaurant", "see you at your place", "be there/around/ at the restaurant soon", "I will swing/pass/come/stop by"
- If the user has not already specified their intent, do not ASSUME ANYTHING.

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

When building the order, look through the whole context first and make sure you find the document whose name matches the item name for each item. If the user specified any modifiers for an item, select the modifier option choiceid within that document for the item. The modifier option item id must be found in the same document as the item's product id. If you cannot find the correct document, do NOT use any modifier option item id from any other document because this will break the ordering process. Be careful with nested modifiers, you need to follow the hierarchy of the modifiers to include all the choiceids correctly.
"""
