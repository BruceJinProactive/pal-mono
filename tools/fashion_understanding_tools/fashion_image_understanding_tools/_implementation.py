import base64
import io
import json
import os
import time
from typing import Union

import requests
from agno.tools.toolkit import Toolkit
from classes import FashionItem, GeneralFunctions, ImageIdentification
from openai import AsyncOpenAI, OpenAI
from PIL import Image

from utils.log import logger

# Load the fashion knowledge base hierarchy
general_functions = GeneralFunctions()
hierarchy = general_functions.get_hierarchy()


class FashionImageUnderstandingTools(Toolkit):
    def __init__(self):
        super().__init__(name="fashion_image_understanding_tools")
        self.register(self._image_understanding)
        # Initialize OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        ### TODO: Define the session data structure with ENG team
        # Placeholder for session data
        self.session_data = {}

    ### TODO: Complete the implementation of the function
    def segment_and_replace_background(
        self, image_bytes: str
    ) -> Union[tuple[str, Image.Image], tuple[None, None], None]:
        return None

    def _image_url_to_base64(self, image_url: str) -> str:
        """Convert an image URL to a base64 encoded image."""
        try:
            response = requests.get(image_url)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"Error converting image URL to base64: {e}")
            return ""

    def _image_identifier(
        self,
        chat_history: list,
        query: str,
        record_time: bool = True,
    ) -> int:
        """This function identifies which image should be used for image understanding task

        Args:
            chat_history (list): The chat history of the user.
            query (str): The user's query.
            record_time (bool): Whether to record the time taken for the function. Defaults to True.

        Returns:
            int: 0 means the image is from the uploaded image, 1 means the image is from the generated image, 2 means the image is from the recommended items.
        """
        ### TODO: Replace session_data with the actual session data structure
        uploaded_image_exists = (
            "base64_image" in self.session_data
            and self.session_data["base64_image"] is not None
        )
        generated_image_exists = (
            "base64_generative_image" in self.session_data
            and self.session_data["base64_generative_image"] is not None
        )

        ### TODO: is there any function we need to call to process the prompt?
        prompt = f"""Role: You are a highly skilled and emotionally intelligent fashion stylist. Your task is to analyze the user’s query and chat history to determine whether the user is referencing an image. Carefully assess the context to make an informed decision.

Instructions:
	1.	Image Reference Detection:
        *	If the user is describing an image, it does not count as a reference to a specific image.
        *	If the user is referencing a specific image, determine its source.
	2.	Source Determination Logic:
        *	Uploaded Image (0): If the user refers to an uploaded image.
        *	Generated Image (1): If the user refers to a previously generated image. Look carefully in the chat history if you see tag _GENERATE_IMAGES_ in the previous round of conversation.
        *	Recommended Items (2): If the user refers to previously recommended items (e.g., phrases like “Love the first one,” “I like the second one,” or “I prefer the third one” with no specific image reference).
	    *	No Image (3): If no image is referenced.
        * If the user asks for similar items, identify the source of the image based on the context.



Extra Information:
	*	The user {'has' if uploaded_image_exists else 'does not have'} uploaded an image.
	*	The system {'has' if generated_image_exists else 'does not have'} generated an image.

Input:
	*	Chat History: {chat_history}
	*	User Query: {query}

Output Format:

{{
    "image_of_interest": <0, 1, 2, or 3>
}}

Output Explanation:
	*	0: Uploaded Image
	*	1: Generated Image
	*	2: Recommended Items
	*	3: No Image
"""
        # Define the json schema for the model
        json_format = ImageIdentification.model_json_schema()
        # Restrict the json schema to the required values
        json_format["properties"]["image_of_interest"]["enum"] = [0, 1, 2, 3]

        start_time = time.time()

        ### TODO: Confirm what is the method to call for openai completion
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt},
            ],
            model="gpt-4o-2024-08-06",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "schema": json_format,
                },
            },
        )
        image_of_interest = chat_completion.choices[0].message.content

        ### TODO: Check which error is raised when the response is empty
        if image_of_interest is None:
            raise ValueError("LLM failed to return a response.")

        image_of_interest = json.loads(image_of_interest)

        if record_time:
            time_taken = time.time() - start_time
            logger.info(f"Time taken to identify the image: {time_taken}")

        if "image_of_interest" in image_of_interest:
            return int(image_of_interest["image_of_interest"])
        else:
            return image_of_interest.values()

    def _lowercase_keys(self, dictionary: dict) -> dict:
        """This function converts all keys in a dictionary to lowercase.

        Args:
            dictionary (dict): The dictionary to convert.

        Returns:
            A new dictionary with all keys converted to lowercase.
        """
        return {k.lower(): v for k, v in dictionary.items()}

    def _image_understanding(
        self,
        image_url: str,
        record_time: bool = True,
    ) -> str:
        """This function analyzes the image to provide a detailed description of the fashion item in the image.

        Args:
            image_url (str): The image url to be analyzed. It should be a direct link to the image.
            record_time (bool): Whether to record the time taken for the function. Defaults to True.

        Returns:
            str: The description of the fashion item in the image. The json schema can be found in the model_json_schema method of the FashionItem class.
        """
        # Record the start time for inference time analysis
        start_time = time.time()

        base64_image = self._image_url_to_base64(image_url)

        ### TODO: Replace session_data with the actual session data structure
        # Initialize the image understandings memory
        if "image_understandings_memory" not in self.session_data:
            self.session_data["image_understandings_memory"] = {}
        if base64_image in self.session_data["image_understandings_memory"]:
            if record_time:
                logger.info(
                    "Time taken to generate image understanding: "
                    + str(time.time() - start_time)
                )
            logger.info(
                "Image understanding from memory: "
                + json.dumps(
                    self.session_data["image_understandings_memory"][base64_image][
                        "image_understanding"
                    ],
                    indent=4,
                )
            )
            return self.session_data["image_understandings_memory"][base64_image][
                "image_understanding"
            ]
        else:
            self.session_data["image_understandings_memory"][base64_image] = {}

        # Segment and remove the background of the image
        try:
            segmented_base64_image = self.segment_and_replace_background(base64_image)
            img_payload = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{segmented_base64_image}",
                },
            }
        except Exception as e:
            logger.error(f"Error segmenting and replacing background: {e}")
            img_payload = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}",
                },
            }

        system_prompt = f"""Analyze the uploaded image to generate the following structured output. Ensure all fields are provided and strictly adhere to the hierarchy.

1. **Image Analysis**:
   - **Categories**: Extract categories of the clothing items visible in the uploaded image (e.g., "outerwear," "footwear") strictly from the hierarchy.
   - **Occasions**: Identify relevant occasions for the clothing items visible in the image (e.g., "formal," "casual") strictly from the hierarchy.
   - **Colors**: Extract color of the clothing items visible in the image. Ignore the model and background. Ignore colors of specific patterns like stripes or polka dots.
   - **Fit features**: Describe the outfit by detailing the fabric, pattern, materials, and key design elements. Include specific structural features such as the neckline, silhouette, and strap style. Mention the length (mini, midi, maxi, long, or short) and any notable design details like ruffles, pleats, lace, or slits. Specify the texture (mesh, satin, velvet) and unique waist details, such as corsets. Use relevant style terms like bodycon, skater, A-line, mermaid, or similar. Highlight sleeve styles (long, short, sleeveless) and back designs (open, backless) as applicable. Include any relevant patterns (e.g., floral, leopard, stripes) based on preferences. Keep descriptions clear, simple, and aligned with the item’s features without unnecessary adjectives or conflicting elements.
   - **Item name**: Identify the name of the item based on the image content.

2. **Hierarchy Compliance**:
   - Use only the predefined hierarchy for selecting `categories`, `occasions`, `colors`, and `fit_features`. Avoid any values outside the hierarchy.

**Hierarchy**:
{hierarchy}

Provide the output in the following JSON structure:
{{
    "categories": ["string", ...],
    "occasions": ["string", ...],
    "colors": ["string", ...],
    "fit_features": ["string", ...]
    "item_name": "string"
}}
"""

        user_content = [{"type": "text", "text": system_prompt}, img_payload]
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": user_content},
            ],
            model="gpt-4o-2024-08-06",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "schema": general_functions._restrict_api_call_params(
                        FashionItem.model_json_schema(), hierarchy=hierarchy
                    ),
                },
            },
        )
        image_understanding = chat_completion.choices[0].message.content
        if image_understanding is None:
            raise ValueError("LLM failed to return a response.")
        image_understanding = json.loads(image_understanding)

        if record_time:
            logger.info(
                "Time taken to generate image understanding: "
                + str(time.time() - start_time)
            )

        logger.info("Image understanding: " + str(image_understanding))

        # Check if we need to iterate to the next layer
        if "properties" in image_understanding:
            image_understanding = image_understanding["properties"]

        # Lowercase the keys
        image_understanding = self._lowercase_keys(image_understanding)

        # Store the image understanding in the session data
        self.session_data["image_understandings_memory"][base64_image][
            "image_understanding"
        ] = image_understanding
        return str(image_understanding)
