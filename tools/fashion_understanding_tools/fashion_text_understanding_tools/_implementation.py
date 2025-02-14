import json
import os

from classes import FashionItem
from openai import AsyncOpenAI, OpenAI
from phi.tools.toolkit import Toolkit


class FashionTextUnderstandingTools(Toolkit):
    def __init__(self):
        super().__init__(name="fashion_text_understanding_tools")
        self.register(self._text_understanding)
        # Initialize OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _text_understanding(
        self,
        query: str,
    ) -> str:
        """Use this function's result to answer a user's query."""

        # Chat history
        chat_history = ""
        # Define prompt
        formatted_prompt = """Based on the user's chat history, query, disliked features, generate a detailed description of the fashion item the user is looking for. Provide the required details in a structured format as outlined below.

    ### Instructions:
    1. **Specific Features Referenced by the User:**
    - When the user references a specific feature from the uploaded image (e.g., "color from the image"):
        - **Prioritize only that feature** as "similar to the image."
        - Keep all other features (e.g., fit, category, occasion) aligned with the user’s textual preferences or default values.

    2. **General Reference to the uploaded or AI-generated image:**
    - If the user requests a general similarity to the image:
        - Set all fields (`item_name`, `colors`, `occasions`, `categories`, `fit_features`) to **"similar to the image."**
        - Ex.: "Looks great, find something similar."

    3. **Requests with Specific Modifications:**
    - If the user specifies changes to features in the image (e.g., "similar to the image but in red"):
        - Retain all fields as "similar to the image" except the specified attribute, which should use the exact value provided (e.g., red from the hierarchy).

    4. **Requests with Specific References:**
        - If the user refers to a specific feature in the uploaded image (e.g., "I love the style of the dress in the uploaded image"):
            - You must write down the feature mentioned in the image (e.g., `categories`, `fit_features`, `item_names`) as "similar to the image.". For the remaining fields, use the user's preferences.
        - When user requests similar 'style', you must write down the `item_name`, `fit_features`, and `categories` as "similar to the image."
        - When user requests similar 'item', you must write down the `item_name`, 'categories' as "similar to the image."
        - When user requests similar 'fit', you must only write down the `fit_features` as ["similar to the image."]
        - When user requests similar 'color', you must only write down the `colors` as "similar to the image."

    5. **No Image Reference:**
    - If the user does not refer to the image:
        - Use the textual query, chat history, and default hierarchy to describe the item's features.
        - Avoid including any disliked features.
        - Do not return "similar to the image" in any field.

    6. **Reference to image from the chat history:**
        - Use "similar to the image" in appropraite fields.
        - Modify based on any new instructions provided by the user.
        - Ex. "find sth similar to the last dress.", "find sth similar to this dress", "love the first one, find sth similar."

    7. **Requests with Exact Item Name Reference:**
        - When the user mentions a specific item name, you must extract and write down the exact `item_name` as the item name mentioned by the user.
            - For example, if user asks for `Aida Glitter Shine Pleated A-Line Dress`, you must write down the `item_name` as "Aida Glitter Shine Pleated A-Line Dress."
        - If the user mentions a specific item name in the query, use the exact item name as the value for the `item_name` field and set all other fields to 'none'.

    Ensure all fields are provided and non-optional. Carefully read through the chat history and query to determine the most relevant and most recent description by the user:

    ### Format for Item Description:
    1. **Item Name**:
    - The type of item the user is looking for (e.g., "dress," "shoes"). Be specific and exclude colors.
    - You must use the exact item name if the user provides it. You must not alter the item name.
    - If the user does not provide an item name, use the most relevant item name based on the context.

    2. **Colors**:
    - Identify the preferred color(s) of the item. If the user specifies a preference, include it. Otherwise, use relevant colors strictly from the hierarchy.
    - If no color preference is specified, return **"none"**.
    - If the user requests to exclude certain colors, list alternative color suggestions strictly from the hierarchy.
    - Avoid any colors explicitly disliked by the user.
    - Choose the most relevant color(s) based on the hierarchy.
    - set to 'none' if the user provides the exact name of the item.

    3. **Occasions**:
    - Extract the primary occasion type(s) (e.g., "formal," "casual") strictly from the hierarchy.
    - If no occasion is specified, return **"none"**.
    - Otherwise, return a list of the most relevant occasion(s) strictly based on the hierarchy.
    - set to 'none' if the user provides the exact name of the item.

    4. **Categories**:
    - Determine the exact clothing or accessory category requested by the user strictly from the hierarchy.
    - If the user specifies a specific category (e.g., "long dresses") or asks for a specific style (e.g., "long ..."), only include that specific subcategory strictly from the hierarchy.
    - If the user asks for a general category (e.g., "dresses"), you must return the general category (e.g., "dresses") strictly from the hierarchy. You could also include the most relevant subcategories based on the context.
    - If no outfit category is mentioned, return **"none"**.
    - set to 'none' if the user provides the exact name of the item.

    5. **Fit Features**:
    - Extract from the user query the outfit's style. Use simple and concise language. Do not include fancy adjectives.
    - Pay attention to what user does not like and avoid those features.
    - In addition to collecting key words from user query, describe the material, patterns, aesthetics that would match with user's preferences if needed. Be detailed, for example, if user asks for a more "casual" style, think about what materials, patterns, and aesthetics would match that style.
    - set to 'none' if the user provides the exact name of the item.

    6. **Product Type**:
    - Determine the type of product the user is looking for. Be specific and exclude colors.
    - set to 'none' if the user provides the exact name of the item.

    """
        formatted_prompt += f"""
    **Strict Guidelines**:
    - Fields `colors`, `occasions`, and `categories` must be strictly selected from the hierarchy. If a user's input suggests an invalid value, use the closest valid value from the hierarchy or return **"none"**.
    - Exclude any disliked attributes mentioned in the chat history.
    - The description is used for database searches; ensure it's precise and concise.
    - Multiple values for `colors`, `occasions`, and `categories` can be provided as a list.
    - Use only the values present in the hierarchy for `colors`, `occasions`, and `categories`.

    Chat History: "{chat_history}"

    User Query: "{query}"

    Format the response in the following JSON structure:
    {{
        "item_name": "string",
        "colors": ["string", ...] or "string",
        "occasions": ["string", ...] or "string",
        "categories": ["string", ...] or "string",
        "fit_features": ["string", ...]
    }}
    """
        user_content_payload = [{"role": "user", "content": formatted_prompt}]

        chat_completion = self.client.chat.completions.create(
            messages=user_content_payload,  # type: ignore
            model="gpt-4o-2024-08-06",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "schema": FashionItem.model_json_schema(),
                },
            },
        )

        # Parse and validate response
        response_content = chat_completion.choices[0].message.content
        if response_content:
            response_dict = json.loads(response_content)
        else:
            response_dict = {}
        return str(response_dict)
