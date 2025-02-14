import json
import os
import time

from classes import FashionItem, GeneralFunctions
from openai import AsyncOpenAI, OpenAI
from phi.tools.toolkit import Toolkit

from utils.log import logger


class ConflictResolution(FashionItem):
    """
    ```json
    {{
        "categories": ["string", ...],
        "occasions": ["string", ...],
        "colors": ["string", ...],
        "fit_features": ["string", ...],
        "item_name": "string",
        "conflicting_features": {{
            "user": ["string", ...],
            "image": ["string", ...]
        }}
    }}
    ```"""

    conflicting_features: dict


# Load utility functions for fashion understanding
general_functions = GeneralFunctions()
hierarchy = general_functions.get_hierarchy()


class FashionConflictResolutionTools(Toolkit):
    def __init__(self):
        super().__init__(name="fashion_conflict_resolution_tools")
        self.register(self._resolve_conflicts)
        # Initialize OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _resolve_conflicts(
        self,
        user_query: str,
        image_understanding: dict,
        text_understanding: dict,
        chat_history: list,
        record_time: bool = True,
    ) -> dict:
        """
        This function resolves the conflicts between the user's query and the image uploaded by the user. Then, suggest the best-matching description of an outfit tailored to the chat history AND user’s query.

        Args:
            image_understanding (dict): The understanding of the uploaded image.
            text_understanding (dict): The understanding of the user's query.
            chat_history (list): The chat history of the session.

        Returns:
            The best occasion, specific occasion, and category of outfit for the user based on the user's query.
        """
        ### TODO: Confirm with ENG team how chat history is being stored and passed to the function
        # Record the start time for inference time analysis
        start_time = time.time()

        system_prompt = f"""Using the provided understanding of the uploaded image, user intents, chat history, and query, identify and address any misalignments between the user’s stated preferences and the attributes of the uploaded image. Develop a detailed analysis and generate a suitable recommendation adhering to the structure below:

### ** Conflict Analysis**
- If you see phrases like 'similar to the image' in the textual understanding, ensure to not include the keys in the conflicting_features. For example, if in the color key of the textual understanding, you see 'similar to the image', ensure to not include the color key in the conflicting_features.
- **`user` key:** Document the features requested in the textual understanding of user query, unless the user specifies a desire for a match based on the uploaded image.
- **`image` key:** Extract and list the key attributes derived from the uploaded image, with a focus on `color`, `occasion`, `category`, and `fit_features`. Treat the image as the primary reference unless the user explicitly requests adjustments.
- **`conflicting_features` key:** Highlight discrepancies between the current user's preferences and the image features, if any. If the user requests an exact or similar match to the image with no modifications, leave this section empty. Otherwise, detail the conflicting features and their resolution. For example, if the user prefers a different color than the one in the image, specify the color conflict and the adjusted color.


### **Discrepancy Resolution:**
    - Clearly identify and articulate modifications when discrepancies exist. For instance:
        - Example 1: “A dress similar to the image but in red.”, where the dress is blue
        - Example 2: “A casual jacket like the one in the image but with a looser fit.”
    - For example 1 you should write 'user': 'red' and 'image': 'blue' in the conflicting_features.
    - For example 2 you should write 'user': 'looser fit' in the conflicting_features.

### **Recommendation Generation:**
   - Combine insights from chat history, textual understanding of the query, and the image analysis to suggest an optimized outfit.
   - Ensure the recommendation aligns with the user's preferences, balancing precision and conciseness.

### **Required Details in the Recommendation:**
   - **Outfit Category:** Suggest the most suitable category.
   - **Occasions:** Recommend appropriate occasions for the outfit.
   - **Colors:** Include suggested colors, considering both the image and user input.
   - **Fit Features:** Highlight fit-specific details such as "loose fit," "tailored," etc.
   - **Item Name:** Provide a specific item name that reflects the combined understanding of preferences and image analysis.

### Output Format:
Respond in the following JSON structure:
```json
{{
    "categories": ["string", ...],
    "occasions": ["string", ...],
    "colors": ["string", ...],
    "fit_features": ["string", ...],
    "item_name": "string",
    "conflicting_features": {{
        "user": ["string", ...],
        "image": ["string", ...]
    }}
}}
```

### Input Details:
- **Chat History:** 
"{chat_history}"

- **Current user Query:** "{user_query}"
- **Image Understanding:** {image_understanding}
- **Textual Understanding of the Query:** {text_understanding}

### Guidelines:
1. **For Similar Match Requests:**  
    - If you see 'similar to the image' in the values of keys textual understanding, ensure to not include the keys in the conflicting_features. You must suggest an outfit that closely matches the image's attributes and ignore user's preferences indicated in chat history or previous queries.

2. **For Adjustments:**  
   - Accurately detail conflicts and their resolution (e.g., adjusting colors, fit, or occasion).
   - Ensure clarity in explaining how the recommendation addresses the user’s preferences.

3. **Smart Integration:**  
   - Use the chat history to refine suggestions and maintain consistency with past preferences unless user refers to an image.
   - Prioritize the latest input when discrepancies or contradictions arise.

By following these guidelines, provide a well-informed and tailored response in the prescribed JSON format. Ensure all conflicts and recommendations are clear, logical, and user-centric.       
"""
        answer = None

        while answer is None:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "user", "content": system_prompt},
                ],
                model="gpt-4o-2024-08-06",
                temperature=0.0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "result",
                        "schema": general_functions._restrict_api_call_params(
                            ConflictResolution.model_json_schema(),
                            hierarchy=hierarchy,
                        ),
                    },
                },
            )
            answer = chat_completion.choices[0].message.content
        answer = json.loads(answer)

        if record_time:
            logger.info(
                "Time taken to resolve conflicts: " + str(time.time() - start_time)
            )

        logger.info("Resolved Conflicts: " + json.dumps(answer, indent=4))
        return answer
