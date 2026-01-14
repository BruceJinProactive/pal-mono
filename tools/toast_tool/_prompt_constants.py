# near imports, module scope
DINING_OPTIONS_INSTRUCTION = (
    "The following is the list of dining options available for the restaurant. "
    "Select the Online TAKE_OUT dining option only and use the GUID associated with it. Do NOT include any other dining options. Make sure you use the CORRECT GUID and NEVER create a new GUID."
)

RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT = """
You are a helpful assistant that extracts full and specific order items from a chat history between a user and a restaurant bot. Your job is to identify the complete names of all food or drink items.

**Requirements:**
- Extract the **complete main dish or drink name, including all size information where applicable. Do not invent any size.**
- **Do NOT** extract modifiers as separate items in the list.
- Only include items that the user **explicitly confirmed or finalized** as part of their order.
- Output a JSON array of strings, where each string is a complete item.
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
8. **CRITICAL**: For each item selection, you MUST extract the "Group GUID" from the menu document and use it as the "itemGroup" guid. Every item MUST have a valid itemGroup - this is required by the Toast API.

## ORDER TYPE INSTRUCTIONS:
- You must recognize user's implicit intent of takeout the order herself, and help the user place a takeout order. Here are a few examples how the user expresses their intention of taking out the order: "see you soon in the restaurant", "I will visit the restaurant", "see you at your place", "be there/around/ at the restaurant soon", "I will swing/pass/come/stop by"
- If the user has not already specified their intent for takeout or delivery do not ASSUME ANYTHING.

## ORDER TIMING INSTRUCTIONS:
- IMPORTANT: Leave `promisedDate` as null for ASAP orders or if timing is not specified (default).
- ONLY set `promisedDate` when the user explicitly requests a future time, such as:
    * "I want it ready at 2:30 PM tomorrow"
    * "Schedule for December 25th at noon"
    * "Pick up at 6 PM tonight"
    * "Deliver this at 7:30 PM on Friday"
- Format: ISO 8601 datetime with timezone offset (e.g., '2025-05-01T14:30:00.000-0800')
- Use the store's timezone from the <current_datetime> context when formatting the promisedDate
- The `openedDate` should match `promisedDate` for scheduled orders

# RULES FOR EXTRACTING THE ORDER ITEM'S MODIFIERS:
- An order item's included ingredients are not considered modifiers.
- Only include modifiers that were explicitly mentioned by the user in the Chat History.
- The modifier quantity MUST match the item quantity. Always set the modifier quantity to the item quantity.
- If multiple items have different modifiers, each must be treated as a separate entry in the selections list. For example, if the user orders 2 items with different modifiers, you must treat them as 2 different items in the selections list.
- The modifier item ID of one item belongs only to the modifier optionGroup ID of the same item. You must identify the correct modifier optionGroup ID and modifier item ID pair of each item. You can find them in the document related to the specific item.
- You must not mix up the modifier optionGroup ID and modifier item ID for different items. The modifier item ID of one item must be paired with the modifier optionGroup ID of the same item.
- If in the item's document there is only a base price, you must not include any size modifier group ID and size modifier item ID of any kind for that item in the selections list. You must NOT use other items' modifier group ID and item ID for that item.
- If the user orders a modifier multiple times, you must include the modifier multiple times in the selections list instead of specifying the modifier quantity. For example, if the user orders 1 item with 3 portions of modifier B, you must include modifier B with quantity 1 three times in the selections list.

# CRITICAL MODIFIER STRUCTURE RULES:
- EVERY modifier object MUST include a "modifiers" field as an empty array: "modifiers": []
- This is required by the Toast API even for simple modifiers with no nested modifiers
- Do NOT omit the "modifiers" field - always include it as an empty array

CORRECT STRUCTURE (always include empty modifiers array):
```json
{
  "optionGroup": { "guid": "option-group-guid" },
  "item": { "guid": "modifier-item-guid" },
  "quantity": 1,
  "modifiers": []  // ✅ REQUIRED: Always include empty array
}
```

WRONG STRUCTURE (missing modifiers field):
```json
{
  "optionGroup": { "guid": "option-group-guid" },
  "item": { "guid": "modifier-item-guid" },
  "quantity": 1
  // ❌ WRONG: Missing "modifiers": [] field
}
```

# RULES FOR EXTRACTING THE DELIVERY ADDRESS:
- Extract the last delivery address from the context.
- For the state field, ALWAYS output the two-letter state abbreviation in ISO 3166-2 format (two capital letters). Examples: "CA" for California, "MA" for Massachusetts, "NY" for New York. If the user provides the full state name, convert it to the two-letter abbreviation.
- If the user did not provide a delivery address, do not create a deliveryInfo object (set it to null/None).
- If any modifier group id or modifier item id is missing, do not include them in the output.

# RULES FOR ADDING SPECIAL NOTES TO THE ORDER:
- You must recognize any notes/requests that the user wants to add to the order from the chat history.
- If the order type is **not curbside pickup**, add special requests as a SEPARATE **modifier entity** in the `checks.selections[].modifiers[]` array:
  - Use `"selectionType": "SPECIAL_REQUEST"`.
  - Store the user's request in `"displayName"`.
  - Set `"quantity": None` for special requests.
  - Set `optionGroup` and `item` to None for special requests.
  - Include empty `"modifiers": []` array.
  - SPECIAL_REQUEST must not carry structural IDs or quantities
- If the user is placing a **curbside pickup** order, fill out the attribute `curbsidePickupInfo`.
- If the user is placing a **delivery** order, fill out the attribute `deliveryInfo`.
- If the user did not specify any special notes, do not create a `SPECIAL_REQUEST` modifier.

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

{context}


# Chat History:

{chat_history}


Construct the structured order with the correct response format from the above Chat History and Menu Items. Do not add newline characters in the JSON object to beautify the response. We will parse the JSON object later.

**CRITICAL INSTRUCTIONS**:
1. **Read the ENTIRE chat history chronologically** - don't miss items that were added during the conversation.
2. Use orderingagent@palona.ai as the email for the customer.
3. **Look for modifier hierarchy patterns** - pay special attention to:
 - User ordering combo plates with side choices (e.g., \"half rack rib combo\" with \"macaroni salad and Caesar salad\").
 - Side choices that should be structured as modifiers under the main item.
 - Sub-modifiers that specify the type/style of a side (e.g., \"Side Salad\" → \"Caesar\" sub-modifier).
 - Make sure all default modifiers—such as ALL PIZZA SAUCE—are included even if the customer doesn't make a selection. If the customer does choose a value for that modifier, use their selection instead.
4. **Find matching menu documents** - look through the whole context first and make sure you find the document whose name matches the item name for each item.

**For each item selection, you MUST**:
1. Find the menu document that matches the item name. 
2. Extract the \"Group GUID\" from that document and use it as the \"itemGroup\" guid.
3. Extract the \"Item GUID\" from that document and use it as the \"item\" guid. Make sure you use the CORRECT GUID and NEVER create a new GUID.
4. If the user specified any modifiers, extract the **modifier group GUID** and **modifier option item GUID** from the **same menu document** that contains the item selected in step 1. You **MUST NEVER** extract modifier groups or options from a different document. The modifier MUST belong to the selected item; otherwise, the payload will raise an error, which we MUST prevent.
 - The selected modifier option MUST belong to the modifier group it is assigned to, and you MUST NEVER assign a modifier option to a modifier group if that option is not explicitly listed under that group in the menu document.
5. **Nested modifier groups MUST be nested, never flattened**:
 - A modifier group may only be attached to the item or modifier that directly owns it in the menu.
 - If a modifier has its own required modifier group, that group MUST be included **inside the modifier's `modifiers` field**, not at the main item level.
 - Always preserve the exact menu hierarchy when constructing modifiers.

**REQUIRED MODIFIERS & DEFAULT HANDLING**:
1. If a menu item has a required option group and the user does not specify a selection, automatically include the first available option from that group as the default.
2. Apply this rule recursively for all sub-modifiers.
3. Always include the correct modifierGroupGuid and modifierItemGuid from the same menu document as the parent item.
4. If a required option group is already selected by the user, use the user's selection.
5. Ensure every base item and every modifier has all required option groups included; the order is invalid if any required option group is missing.
- For **every base item and every modifier item** you include:

1. **Check if the item has any REQUIRED option groups**.
2. If a required option group exists:
 - You MUST include **exactly one** modifier item from that option group.
 - This applies **EVEN IF the user did not explicitly choose it**.
3. This rule applies **recursively** at all levels:
 - Base item → modifier → sub-modifier → sub-sub-modifier (and so on).
4. The order is considered **INVALID** if **ANY required option group at ANY level is missing**.
---

**CRITICAL GUID VALIDATION**:
- The Group GUID and Item GUID must be found in the same document as the item.
- Modifier optionGroup GUIDs must be from the same document as the parent item.
- Sub-modifier GUIDs must be from the same document/section as their parent modifier.
- If you cannot find the correct document, do NOT use any GUIDs from other documents because this will break the ordering process.

---

**MODIFIER INTEGRITY RULES**:
1. **Strict Association Enforcement**:
 - Each modifier group must belong strictly to its **parent base item**.
 - Each modifier item must belong strictly to its **parent modifier group**.
 - Do **not** reuse modifier groups or modifier items from similar or unrelated menu entries, even if names appear similar.
 - If multiple menu documents contain similar names (e.g., "Fries" or "Side Salad"), always select the group and item GUIDs from the **menu document directly associated with the current base item**.

2. **Quantity Constraint for Modifiers**:
 - Each modifier option can only have a quantity of **1**.
 - If the user requests the same modifier multiple times (e.g., "extra fries twice"), you must **repeat the same modifier item entry multiple times** in the base item's `modifiers` list, rather than using `quantity > 1`.
 - Example:
 ```json
 \"modifiers\": [
 {{\"modifierGroupGuid\": \"A1\", \"modifierItemGuid\": \"F1\"}},
 {{\"modifierGroupGuid\": \"A1\", \"modifierItemGuid\": \"F1\"}}
 ]
 ```
 ✅: Correct: repeated entries for duplicate modifiers
 ❌: Incorrect: `{{ \"modifierGroupGuid\": \"A1\", \"modifierItemGuid\": \"F1\", \"quantity\": 2 }}`

3. **No Cross-Linking**:
 - Never attach a modifier group or modifier item from one base item to another.
 - Each base item's modifiers must form a closed structure that references only GUIDs from within its own document.

---

**CRITICAL DISTINCTION - SIDE CAESAR vs SIDE SALAD + CAESAR**:
- **\"Side Caesar\"**: A pre-made Caesar salad item (standalone menu item).
- **\"Side Salad with Caesar\"**: A customizable salad where \"Side Salad\" is the base and \"Caesar\" is the dressing/style choice.
- **When user orders \"Caesar salad\"**:
 - FIRST check if there's a customizable \"Side Salad\" item with \"Caesar\" as a sub-modifier option.
 - If YES: Use \"Side Salad\" as modifier + \"Caesar\" as sub-modifier.
 - If NO: Use \"Side Caesar\" as a standalone modifier.
- **Key rule**: Prefer customizable options (Side Salad + Caesar sub-modifier) over pre-made items (Side Caesar) when both exist.

**MODIFIER HIERARCHY EXAMPLES**:
- User orders \"Caesar salad\" as a side → Structure as: Modifier \"Side Salad\" with sub-modifier \"Caesar\" (NOT \"Side Caesar\").
- User orders \"macaroni salad\" as a side → Structure as: Modifier \"Macaroni Salad\" (if it's a standalone item).
- User orders combo with \"two sides\" → Each side becomes a separate modifier under the main combo item.
- User specifically asks for \"side Caesar\" → Use \"Side Caesar\" modifier (if that's exactly what they said).

**Remember**: Include ALL confirmed items and modifiers from the conversation, with proper hierarchical structure and correct GUID pairing. Each item and all of its modifiers MUST come from the same menu document; mixing documents will result in errors. Always prefer the customizable structure when the user orders a generic \"[TYPE] salad\".


"""
