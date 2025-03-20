import json
import time
import traceback
from typing import List

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI, OpenAI

from utils.log import logger

from ..classes import GeneralFunctions, NegativeFashion

general_functions = GeneralFunctions()


class FashionNegativeIntentTools:

    def __init__(self, hierarchy: dict, client: OpenAI, client_async: AsyncOpenAI):
        # Initialize OpenAI
        self.client = client
        self.client_async = client_async
        ### TODO: Define the session data structure with ENG team
        # Placeholder for session data
        self.session_data = {}

        self.hierarchy = hierarchy

    @task(name="Detect Negative Intents")
    def _detect_negative_intents(
        self, query: str, chat_history: List | str, record_time: bool = True
    ) -> dict:
        """
        Detects negative intents in the user query and chat history, returning a dictionary of attributes to exclude.

        Args:
            query (str): The exact query entered by the user.
            chat_history (List): The chat history containing past user preferences and dislikes.

        Returns:
            dict: A dictionary where keys are categories (e.g., "color") and values are lists of items (e.g., ["blue"]) to exclude.
        """

        start_time = time.time()

        # Call OpenAI to identify negative intents based on both query and chat history
        user_prompt = f"""Analyze the user's query and chat history to identify features that the user does not want to see in the recommendations. You should select from the hierarchy specific undesired attributes, including colors, occasions, categories, materials, patterns, fit or style preferences, aesthetics, and other features. Only extract dislikes that user explicitly or implicitly mentioned.

Key Instructions:
**Fields to Extract:**
- "occasion": Disliked contexts or settings for use (e.g., formal, casual, party, etc). Select from the existing hierarchy.
- "category": Disliked product types (e.g., plunging, midi, maxi, etc). Select from the existing hierarchy.
- "color": Colors the user dislikes (e.g., red, neon, pastel tones, etc). Select from the existing hierarchy.
- "material": Materials the user dislikes (e.g., leather, wool, silk, etc).
- "patterns": Patterns the user dislikes (e.g., floral, stripes, polka dots, etc).
- "disliked_fit_style": Specific fit or style dislikes (e.g., crop tops, bodycon dresses, plunging necklines, etc).
- "aesthetics": Broader disliked aesthetics or finishes (e.g., glittery, shiny, minimalist, etc).

**Critical Requirements:**
- **Explicit Mentions:** Capture dislikes explicitly stated by the user.
- **Implicit Mentions:** Deduce dislikes if strongly implied by the user's input.
- **Multiple Categories:** Include attributes in all relevant fields where applicable.
- **Hierarchy Alignment:** Use the existing hierarchy for occasions, categories, and colors. Do not invent new attributes outside the hierarchy.
- **Distinction Between Likes and Dislikes:** Carefully separate preferences from dislikes. For example: "I like pastel colors but hate neon shades" should extract "neon shades" under "color" and ignore "pastel colors; Recommend midi skirt with no glitter" should extract "glitter" under "fit_style" and ignore "midi skirt. etc"
- **Avoid Hallucination:** Be critical, if the dislikes extracted from the user's query do not match with the fields , you must return `None` for the related fields. If they do not match with all the fields, return `None` for all fields. Do not infer dislikes that are not present in the input.

**Additional Scenarios:**
- Handle mixed statements by separating dislikes from likes.
- Map generalized phrases like "I’m not a fan of bold designs" to the appropriate fields, such as "patterns" or "aesthetic."

Chat history: 
{chat_history}

Current query: 
{query}

Hierarchy: 
{self.hierarchy}


**Output Format:**
Return in this JSON structure:
```json
{{
    "occasion": [...] | None,
    "category": [...] | None,
    "color": [...] | None,
    "material": [...] | None,
    "patterns": [...] | None,
    "disliked_fit_style": [...] | None,
    "aesthetics": [...] | None,
}}
```
"""

        if self.session_data.get("prev_negative_intents") is not None:
            user_prompt += (
                "You will also be provided with the previous disliked features. Use the following guidelines to manage disliked features: "
                "determine whether each previous disliked feature remains relevant based on the current query and chat history; "
                "retain relevant disliked features in the response; exclude irrelevant intents or those that the user has explicitly or implicitly re-included in their preferences. "
                "Ensure the response accurately reflects the user's current dislikes while removing outdated or irrelevant features."
                f"\nPrevious disliked features: {self.session_data.get('prev_negative_intents')}"
            )

        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": user_prompt},
            ],
            model="gpt-4o-2024-08-06",
        )
        # Process and normalize the response content
        answer = chat_completion.choices[0].message.content
        if answer is None:
            raise ValueError("GPT failed to generate a response.")

        # Extract the list of recommended items between ```json``` tags
        try:
            answer = (
                answer.split("```json")[1]
                .split("```")[0]
                .strip()
                .replace("'", '"')
                .replace("None", "null")
            )
            logger.info(answer)
            answer = json.loads(answer)
        except (json.JSONDecodeError, KeyError):
            traceback.print_exc()
            raise ValueError("GPT failed to generate a valid response")

        logger.info(f"Negative intents detected: {answer}")
        # Use pydantic model to validate the response
        try:
            NegativeFashion.model_validate(answer)
        except Exception as e:
            logger.error(f"Error validating negative intents: {e}")
            raise ValueError("GPT failed to generate a valid response")

        # Remove all keys with None values
        answer = {k: v for k, v in answer.items() if v is not None}

        for key in answer:
            if answer[key] is not None:
                logger.info("negative intents: " + key + " : " + str(answer[key]))
                if isinstance(answer[key], list):
                    answer[key] = [i.lower() for i in answer[key]]
                else:
                    try:
                        answer[key] = answer[key].lower()
                    except Exception:
                        logger.error(f"Error converting {key} to lower case")
                        logger.error(answer[key])
                        answer[key] = []

        # Record the time taken for the operation
        if record_time:
            logger.info(
                f"Time taken to detect negative intents: {time.time() - start_time} seconds"
            )

        self.session_data["prev_negative_intents"] = answer
        LLMObs.annotate(
            input_data={"query": query, "chat_history": chat_history},
            output_data=answer,
            tags={"windsor": "test"},
        )
        return answer
