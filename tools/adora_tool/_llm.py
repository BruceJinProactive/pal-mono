from typing import TypeVar, overload

from agno.agent.agent import Agent
from agno.models.groq.groq import Groq
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm
from pydantic import BaseModel

RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT = """You are a helpful assistant that extracts full and specific order items' names from a chat history between a user and a restaurant bot. Your job is to identify the complete names of all food or drink items the user has added to their final order.
Requirements:
- Extract the **complete dish or drink name**, but **remove size or quantity information**.
- Do not shorten or generalize the dish.
- Only include items that the user **explicitly confirmed or finalized** as part of their order.
- Output a JSON array of strings with **cleaned item names**.
"""

EXTRACTOR_SYSTEM_PROMPT = """You are an expert at structured data extraction.
You will be given the chat history and relevant context. You goal is to convert it into the given structure.

# INSTRUCTIONS FOR THE TASK:
1. Identify if the user wants to order for delivery or pickup. If it's delivery, identify the delivery address. If it's pickup, leave the address field empty.
2. Identify the list of order items that the user wants to order from the chat history.
3. Make sure that the quantities for each order are correct.
4. Make sure that the modifiers for every order are identified, if they were mentioned in the chat history. Modifiers are additional details about the order, such as "extra cheese" or "no onions". They are not the already included ingredients of an item.
5. Map the items, names, modifiers, etc., that you identified from the english language to the structured data format that is required by the Adora API using the provided context.
6. Make sure that the order type is correctly identified as "TakeOut" or "Delivery". If not specified it should be empty.
7. Extract discount coupon codes if available.

## ORDER TYPE INSTRUCTIONS:
- You must recognize user's implicit intent of takeout the order herself, and help the user place a takeout order. Here are a few examples how the user expresses their intention of taking out the order: "see you soon in the restaurant", "I will visit the restaurant", "see you at your place", "be there/around/ at the restaurant soon", "I will swing/pass/come/stop by"
- You must recognize user's implicit intent of having the order delivered, and help the user place a delivery order. Here are a few examples how the user expresses their intention of getting the order delivered: send it over; Can not wait for it to get here; I'll be waiting for it; I'll be here to receive it; send it my way/to my place; Let me know when it's out for delivery; waiting for the drop-off"
- If the user has not already specified their intent for takeout or delivery do not ASSUME ANYTHING.

# RULES FOR EXTRACTING THE DELIVERY ADDRESS:
- Extract the last delivery address from the context.
- For the state field, if the user provides an abbreviation, output the full state name, i.e., if the user entered "CA", output "California".
- If any field is missing, output "N/A" for that field, i.e., if the user did not
provide a delivery address, output "N/A" for all fields.

# RULES FOR EXTRACTING THE ORDER ITEM'S MODIFIERS:
- An order item's included ingredients are not considered modifiers.
- Only include modifiers that were explicitly mentioned by the user in the Chat History.

# IMPORTANT RULES:
- Do NOT make assumptions or fabricate data
- Leave fields as None/null if the information is not explicitly mentioned
- Do not infer values or make educated guesses
- Only extract information that is directly stated
- Maintain exact values as mentioned (don't modify numbers or text)
  If a single name is provided (without clarification), always treat it as the first name.
- For phone numbers, only extract if a complete number is provided
- For addresses, only extract if all required components are present
- You must ALWAYS extract the `item_id` and `size_id` for an item. Use the relevant context to identify the CORRECT `item_id` and `size_id` for each item.

If unsure about any field, leave it empty rather than guessing.
"""

DISCOUNT_SYSTEM_PROMPT = """# Discount:
There are secret discounts that can be applied to the order. If the user mentions the discount_code in the chat history, you must apply it to the order by populating the `coupon_ids` with the associated "coupon_id". The discount code is case-insensitive, so "abc" and "ABC" are considered the same.

The discount codes are:
{discounts}

### Examples for single word discount codes:

If the discount codes are:
1. discount code "abc" with coupon_id 123
2. discount code "xyz" with coupon_id 456

** Example 1 **
User: "I have a discount code ABC"
Agent: "Awesome! I'll apply your secret discount at checkout."

You should populate the `coupon_ids` with [123].

** Example 2 **
User: "XYZ"
Agent: "Awesome! I'll apply your secret discount at checkout."
User: "abc"
Agent: "Awesome! I'll apply your secret discount at checkout."

You should populate the `coupon_ids` with [456, 123].
However, there may be multiple coupon codes mentioned in the chat history, you should extract all of them and populate the `coupon_codes` with all of them. Do not mistake the coupon_ids for coupon_codes.
"""

EXTRACTOR_USER_PROMPT = """
# Menu Items With Corresponding Modifiers:
<documents>
{context}
</documents>

# Chat History:
<history>
{chat_history}
</history>

Please construct the structured order from the above Chat History and Menu Items.
"""

T = TypeVar("T", bound=BaseModel)


@overload
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T],
    name: str = "tool",
    reasoning: bool = True,
) -> T | None: ...


@overload
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: None = None,
    name: str = "tool",
    reasoning: bool = True,
) -> str | None: ...


@llm(name="get_structured_outputs")
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None = None,
    name: str = "tool",
    reasoning: bool = True,
) -> T | str | None:
    model_name = (
        "deepseek-r1-distill-qwen-32b" if reasoning else "llama-3.3-70b-versatile"
    )
    client = Groq(id=model_name)

    if response_format:
        system_prompt += """
        \n
        Structure your response as a dictionary, do not include "json" in the beginning
        of the response.
        """

    # Deepseek models works better if everything is passed in the user prompt
    if "deepseek" in model_name:
        prompt = "\n\n".join([system_prompt, prompt])
        system_prompt = ""

    agent = Agent(
        model=client,
        agent_id=f"ordering-tools/{name}",
        session_id="test-session",
        add_history_to_messages=True,
        knowledge=None,
        response_model=response_format,
        system_message=system_prompt,
        num_history_responses=0,
        search_knowledge=False,
    )

    response = agent.run(prompt).content

    LLMObs.annotate(
        input_data=prompt,
        output_data=str(response),
        metadata={"system_prompt": system_prompt},
    )

    return response
