import json
import time
from typing import List

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI, OpenAI

from utils.log import logger

from ..classes import FashionItem, GeneralFunctions, ImageIdentificationOutput

general_functions = GeneralFunctions()


class FashionTextUnderstandingTools:
    def __init__(self, hierarchy: dict, client: OpenAI, client_async: AsyncOpenAI):
        self.hierarchy = hierarchy
        # Initialize OpenAI
        self.client = client
        self.client_async = client_async

    @task(name="Text Understanding")
    def _text_understanding(
        self,
        chat_history: List | str,
        query: str,
        past_recommendations: list | None = None,
        prev_user_preferences: str | None = None,
        negative_intents: dict | None = None,
        record_time: bool = True,
        image_to_analyze: int = ImageIdentificationOutput.NO_IMAGE,
    ) -> dict:
        # Record the start time for inference time analysis
        start_time = time.time()

        # This is kept as a dictionary to improve readability
        choose_which_image_mapping = {
            0: "The user is referring to the uploaded image. Follow the instructions to generate the description based on the uploaded image.",
            1: "The user is referring to an image from the chat history. Follow the instructions to generate the description based on the image from the chat history.",
            2: "The user is describing the item without referring to any image. Follow the instructions to generate the description.",
        }
        logger.info(f"Context: {choose_which_image_mapping[image_to_analyze]}")
        # Define prompt
        formatted_prompt = f"""Based on the user's chat history, query, and hierarchy, infer a detailed description of the fashion item the user is looking for.
        
### Context:
{choose_which_image_mapping[image_to_analyze]}

### Instructions:
**Specific Features Referenced by the User:**
   - When the user references a specific feature from the uploaded image (e.g., "color from the image"):
     - **Prioritize only that feature** as "similar to the image."
     - Keep all other features (e.g., fit, category, occasion) aligned with the user’s textual preferences or default values.

**General Reference to the uploaded image:**
   - If the user requests a general similarity to the image:
     - Set all fields (`item_name`, `colors`, `occasions`, `categories`, `fit_features`) to **"similar to the image."**
     - Ex.: "Looks great, find something similar."

**Requests with Specific Modifications:**
   - If the user specifies changes to features in the image (e.g., "similar to the image but in red"):
     - Retain all fields as "similar to the image" except the specified attribute, which should use the exact value provided (e.g., red from the hierarchy).

**Requests with Specific References:**
    - If the user refers to a specific feature in the uploaded image (e.g., "I love the style of the dress in the uploaded image"):
        - You must write down the feature mentioned in the image (e.g., `categories`, `fit_features`, `item_names`) as "similar to the image.". For the remaining fields, use the user's preferences.
    - When user requests similar 'style', you must write down the `item_name`, `fit_features`, and `categories` as "similar to the image."
    - When user requests similar 'item', you must write down the `item_name`, 'categories' as "similar to the image."
    - When user requests similar 'fit', you must only write down the `fit_features` as ["similar to the image."]
    - When user requests similar 'color', you must only write down the `colors` as "similar to the image."

**No Image Reference:**
   - If the user does not refer to the image:
     - Use the textual query, chat history, and default hierarchy to describe the user's most recent preferences.
     - Avoid including any disliked features you could infer from the chat history and query. Note that the user may ask in the current for an item with features they disliked.
     - Do not return "similar to the image" in any field.

**Reference to image from the chat history:**
    - Use "similar to the image" in appropraite fields.
    - Modify based on any new instructions provided by the user.
    - Ex. "find sth similar to the last dress.", "find sth similar to this dress", "love the first one, find sth similar."

**Requests with Exact Item Name Reference:**
    - When the user mentions a specific item name, you must extract and write down the exact `item_name` as the item name mentioned by the user.
        - For example, if user asks for `Aida Glitter Shine Pleated A-Line Dress`, you must write down the `item_name` as "Aida Glitter Shine Pleated A-Line Dress."
    - If the user mentions a specific item name in the query, use the exact item name as the value for the `item_name` field and set all other fields to 'none'.
     
Ensure all fields are provided and non-optional. Carefully read through the chat history and query to determine the most relevant and most recent description by the user:

### Format for Item Description:
**Item Name**: 
   - The type of item the user is looking for (e.g., "dress," "shoes"). Be specific and exclude colors.
   - You must use the exact item name if the user provides it. You must not alter the item name.
   - If the user does not provide an item name, use the most relevant item name based on the context.

**Colors**:
   - Strictly select from the hierarchy the colors the user might be interested in. If the user specifies a preference, include it.
   - If no color preference is specified, return the color(s), use the most recent color preference(s) indicated by the user. If no color preference is found from the chat history, return **"none"**.
   - If the user requests to exclude certain colors, list alternative color suggestions strictly from the hierarchy.
   - Avoid any colors explicitly disliked by the user unless the user asks for an item with those colors in the current query.
   - Set to 'none' if the user provides the exact name of the item.

**Occasions**:
   - Strictly select from the hierarchy the primary occasion type(s) (e.g., "formal," "casual").
   - If no occasion is specified, return **"none"**.
   - Otherwise, return a list of the most relevant occasion(s) strictly based on the hierarchy.
   - Set to 'none' if the user provides the exact name of the item.

**Categories**:
   - Determine the exact clothing or accessory category requested by the user strictly from the hierarchy.
   - If the user specifies a specific category (e.g., "long dresses") or asks for a specific style (e.g., "long ..."), only include that specific subcategory strictly from the hierarchy.
   - If the user asks for a general category (e.g., "dresses"), you must return the general category (e.g., "dresses") strictly from the hierarchy. You could also include the most relevant subcategories based on the context.
   - If no outfit category is mentioned, return **"none"**.
   - Set to 'none' if the user provides the exact name of the item.

**Fit Features**:
   - Analyze the user query and chat history to infer outfit styles of interest. Use simple and concise language. Do not include fancy adjectives.
   - Pay attention to what user does not like and do not include those features in the output.
   - In addition to collecting key words from user query, describe the material, patterns, aesthetics that would match with user's preferences if needed. Be detailed, for example, if user asks for a more "casual" style, think about what materials, patterns, and aesthetics would match that style.
   - Set to 'none' if the user provides the exact name of the item.
   
**Product Type**:
    - Determine the type of product the user is looking for. Be specific and exclude colors.
    - Set to 'none' if the user provides the exact name of the item.

"""
        # Define instructions for handling previous user preferences
        if prev_user_preferences:
            logger.info(f"Previous User Preferences: {prev_user_preferences}")
            prev_user_preferences_instructions = """You have access to the user's previous preferences and interactions. When responding to the current query, carefully evaluate whether these prior preferences are relevant and, if so, seamlessly incorporate them into your response. Pay attention to what user does not like and avoid those features. Ensure that the response is consistent with the user's most recent input and preferences.

### Guidelines:
**Relevance of Preferences:**
   - If the user’s query specifies a unique or situational context (e.g., referring to an uploaded image), prioritize details specific to the query.

**Handling Specific Cases:**
   - **Similar Items to Uploaded Image:**
     - If the user requests items similar to an uploaded image, prioritize "similar to the image" in fields like `item_name`, `colors`, `occasions`, `categories`, and `fit_features`. Do not include previous preferences.
   - **Similar ... to Uploaded Image:**
     - If the user requests items in a similar ... to the uploaded image, prioritize those features as "similar to the image" as instructed earlier.
   - **Referring to a Specific Item:**
     - When the user references a specific item, retrieve its details from the chat history and previous recommendations. Provide precise information on `color`, `occasion`, `category`, and `fit_features`, but exclude unrelated prior preferences.

**Smart Integration:**
   - Use contextual awareness to balance user-provided information with historical preferences.
   - Adapt dynamically: If the user modifies their preferences or provides conflicting details, prioritize the most recent input while maintaining consistency.
   - If previous preferences contain the feature the user is trying to avoid, exclude those features from the current response.

### Example Scenarios:
**User Previously Specified Preferences:**  
   - Query: “Show me a similar style to the last dress.”  
   - Response: Include style from the previous dress and add prior preferences (e.g., preferred colors or occasions) for unspecified details.

**User Refers to an Uploaded Image:**  
   - Query: “Find items like this image.”  
   - Response: Use “similar to the image” in relevant fields without integrating previous preferences.  

**User Refers to a Specific Feature:**
    - Query: “I love the style of the uploaded image.”
    - Response: Prioritize the `item_names`, `categories`, and `fit_features` as similar to the image. For other fields, use the user's preferences or default values.
    - Refer to previous instructions for how to handle other specific features such as 'colors', 'categories', 'occasions', 'item_names', and 'fit_features'.
    
**User Refers to a Specific Item:**  
   - Query: “What were the details of the jacket I liked before?”  
   - Response: Provide exact details (e.g., material, fit, color) without integrating other preferences.

**User Refers to the exact name of the item:**
    - Query: "I want the 'Ainsley Glittering Evening Gown'."; return {"item_name": "Ainsley Glittering Evening Gown", "colors": 'none', "occasions": 'none', "categories": 'none', "fit_features": []}
            
"""
            formatted_prompt += prev_user_preferences_instructions

        formatted_prompt += f"""
### **Strict Guidelines**:
- Fields `colors`, `occasions`, and `categories` must be strictly selected from the hierarchy. If a user's input suggests an invalid value, use the closest valid value from the hierarchy or return **"none"**.
- Exclude any disliked attributes mentioned in the chat history unless the user asks for an item with such attributes in the current query.
- The description is used for database searches; ensure it's precise and concise.
- Multiple values for `colors`, `occasions`, and `categories` can be returned as a list.
- Use only the values present in the hierarchy for `colors`, `occasions`, and `categories`.

Chat History: 
{chat_history}

User Query: 
{query}

Past Recommendations: "{past_recommendations}"

Hierarchy:
{json.dumps(self.hierarchy)}

Format the response in the following JSON structure:
```json
{{
    "item_name": "string",
    "colors": ["string", ...] or "string",
    "occasions": ["string", ...] or "string",
    "categories": ["string", ...] or "string",
    "fit_features": ["string", ...]
}}
```
"""
        chat_completion = self.client.chat.completions.create(
            messages=[{"role": "user", "content": formatted_prompt}],
            model="gpt-4o-2024-08-06",
        )

        # Parse and validate response
        response_content = chat_completion.choices[0].message.content
        if response_content is None:
            raise ValueError("GPT failed to generate a response")

        # Extract the list of recommended items between ```json``` tags
        try:
            answer = (
                response_content.split("```json")[1]
                .split("```")[0]
                .strip()
                .replace("'", '"')
                .replace("None", "null")
            )
            response_dict = json.loads(answer)
        except (json.JSONDecodeError, KeyError):
            raise ValueError("GPT failed to generate a valid response")

        # Use pydantic model to validate the response
        try:
            FashionItem.model_validate(response_dict)
        except Exception as e:
            raise ValueError(f"GPT failed to generate a valid response: {e}")

        # Log the time taken for text understanding
        if record_time:
            logger.info(
                "Time taken for text understanding: {:.2f} seconds".format(
                    time.time() - start_time
                )
            )

        logger.info(f"Text understanding of user preference :\n{response_dict}")

        LLMObs.annotate(
            input_data={
                "query": query,
                "chat_history": chat_history,
            },
            output_data=response_dict,
            tags={"windsor": "test"},
        )
        return response_dict
