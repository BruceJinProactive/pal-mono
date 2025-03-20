import copy
import json
import os
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from agno.storage.agent.session import AgentSession
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, task, tool
from openai import AsyncOpenAI, OpenAI

from agent.legacy.storage import get_storage
from utils.log import logger

from .classes import (
    AntonymsofNegativeFashion,
    CloseUpItem,
    GeneralFunctions,
    ImageIdentificationOutput,
    PastImageIdentifier,
)
from .fashion_conflict_resolution_tools import FashionConflictResolutionTools
from .fashion_image_understanding_tools import FashionImageUnderstandingTools
from .fashion_negative_intent_detection_tools import FashionNegativeIntentTools
from .fashion_rag_search_filter_utils_tools import FashionRagSearchFilterUtilsTools
from .fashion_reranker_tools import FashionRerankerTools
from .fashion_session_data_tools import FashionSessionDataTools
from .fashion_text_understanding_tools import FashionTextUnderstandingTools

# Set to True to record and see the time taken for each function in docker logs
RECORD_TIME = False

MAX_COLOR_AMBIGUITY = 3


def generate_ids_uuid():
    # Generate a random UUID for user ID
    user_id = str(uuid.uuid4())

    # Generate another random UUID for session ID
    session_id = str(uuid.uuid4())

    return user_id, session_id


def load_json_from_file(file_path) -> dict[Any, Any] | Any:
    # Check if file is empty
    if not os.path.exists(file_path) or os.stat(file_path).st_size == 0:
        # Return an empty dict or some default
        return {}

    with open(file_path, "r") as f:
        return json.load(f)


class FashionRecommendationLogicPipeline(Toolkit):
    def __init__(
        self,
        store_id: str,
        agent_id: uuid.UUID,
        account_id: uuid.UUID,
        account_name: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        namespace: str,
    ):
        super().__init__(name="fashion_recommendation_logic_pipeline")
        self.register(self._recommendation_logic)
        self.register(self.get_close_up_images)

        self.account_name = account_name
        self.user_id = user_id
        self.session_id = session_id
        self.agent_id = agent_id
        self.account_id = account_id
        self.namespace = namespace

        # Initialize OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        ### TODO: Define the session data structure with ENG team
        self.ENABLE_SESSION_DATA = True

        # Initialize fashion hierarchy
        self.general_functions = GeneralFunctions()
        self.hierarchy = self.general_functions.get_hierarchy()

        # Initialize tools classes
        self.fashion_negative_intent_tools = FashionNegativeIntentTools(
            hierarchy=self.hierarchy, client=self.client, client_async=self.client_async
        )
        self.fashion_image_understanding_tools = FashionImageUnderstandingTools(
            hierarchy=self.hierarchy, client=self.client, client_async=self.client_async
        )
        self.fashion_text_understanding_tools = FashionTextUnderstandingTools(
            hierarchy=self.hierarchy, client=self.client, client_async=self.client_async
        )
        self.fashion_conflict_resolution_tools = FashionConflictResolutionTools(
            hierarchy=self.hierarchy, client=self.client, client_async=self.client_async
        )
        self.rag_search_filter_utils_tools = FashionRagSearchFilterUtilsTools(
            hierarchy=self.hierarchy, client=self.client, client_async=self.client_async
        )
        self.fashion_reranker_tools = FashionRerankerTools(
            client=self.client, client_async=self.client_async
        )
        self.fashion_session_data_tools = FashionSessionDataTools(
            client=self.client, client_async=self.client_async
        )

    @retrieval
    def _get_session_data(self) -> Dict[str, Any]:
        storage = get_storage(self.account_name)
        session_data = storage.read(str(self.session_id), str(self.user_id))
        if not session_data:
            logger.error(
                "Session data not found for\n"
                f"Account Name: {self.account_name}\n"
                f"Account ID: {self.account_id}\n"
                f"Agent ID: {self.agent_id}\n"
                f"User ID: {self.user_id}\n"
                f"Session ID: {self.session_id}"
            )
            return {}
        logger.info(f"Retrieving session data: {session_data.session_data}")
        session_data = session_data.session_data
        if not session_data:
            return {}
        LLMObs.annotate(
            output_data=session_data,
            tags={"windsor": "test"},
        )

        return session_data

    def _write_session_data(self, session_data: Dict[str, Any]) -> None:
        storage = get_storage(self.account_name)
        session = storage.read(str(self.session_id), str(self.user_id))
        if not session:
            logger.error(
                "Session data not found for\n"
                f"Account Name: {self.account_name}\n"
                f"Account ID: {self.account_id}\n"
                f"Agent ID: {self.agent_id}\n"
                f"User ID: {self.user_id}\n"
                f"Session ID: {self.session_id}"
            )
        session = AgentSession(
            session_id=str(self.session_id),
            agent_id=str(self.agent_id),
            user_id=str(self.user_id),
        )
        logger.info(f"Writing session data: {session_data}")
        session.session_data = session_data
        storage.upsert(session)

    def _get_user_content(self, text: str) -> str:
        match = re.search(r"<content>\s*(.*?)\s*</content>", text)
        return match.group(1) if match else ""

    def _get_assistant_content(self, text: str) -> str:
        try:
            response = json.loads(text)["content"]
            return response
        except (json.JSONDecodeError, KeyError):
            logger.error(f"Error in getting assistant content: {text}")
            return ""

    @retrieval
    def _get_chat_history(self) -> str:
        try:
            try:
                # TODO: Defer import to avoid circular import
                storage = get_storage(self.account_name)
                agent_session = storage.read(str(self.session_id), str(self.user_id))

                if not agent_session:
                    logger.error(
                        "Agent chat history not found for\n"
                        f"Account Name: {self.account_name}\n"
                        f"Account ID: {self.account_id}\n"
                        f"Agent ID: {self.agent_id}\n"
                        f"User ID: {self.user_id}\n"
                        f"Session ID: {self.session_id}"
                    )
                    return ""

                messages = agent_session.memory["runs"]  # type: ignore

                chat_history = ""

                for message in messages:
                    role = message["message"]["role"]
                    if role == "user":
                        user_content = (
                            self._get_user_content(message["message"]["content"])
                            or message["message"]["content"]
                        )
                        chat_history += f"**[User]**\n{user_content}\n\n"
                        assistant_content = (
                            self._get_assistant_content(message["response"]["content"])
                            or message["response"]["content"]
                        )
                        chat_history += f"**[Assistant]**\n{assistant_content}\n\n"
                    else:
                        logger.info(
                            f"Skipping appending message to chat history:\n{message}"
                        )
                logger.info(f"Chat history: {chat_history}")
                LLMObs.annotate(
                    output_data=chat_history,
                    tags={"windsor": "test"},
                )
                return chat_history

            except ValueError:
                logger.error(
                    "Conversation history not found for\n"
                    f"Account ID: {self.account_id}\n"
                    f"Agent ID: {self.agent_id}\n"
                    f"User ID: {self.user_id}\n"
                    f"Session ID: {self.session_id}"
                )
                return ""

        except Exception as e:
            error_msg = "Error in getting chat history"
            logger.error(f"{error_msg}: {e}")
            return ""

    def _generate_countdown_deal(self) -> str:
        """Generate a random countdown deal to create the sense of urgency"""
        total = 30
        set_countdown_mins = {5, 10, 15, 20}
        int_countdown_mins = random.choice(list(set_countdown_mins))
        int_percentage = int(total - int_countdown_mins)
        str_countdown_mins = str(int_countdown_mins)
        str_percentage = str(int_percentage)
        str_final = f"In addition, create a sense of urgency by telling the user that, if the user purchases the product in {str_countdown_mins} minutes, the user will get an extra {str_percentage} percent off on this product. And this offer is exclusive to the user only."
        return str_final

    @task(name="Get Close Up Images")
    def get_close_up_images(self, query: str) -> str:
        """This function provides a close-up view of the previously recommended fashion items based on the user's query.

        Args:
            query (str): The exact query entered by the user.

        Returns:
            The fashion item user selected for a closer view.

        **Trigger Conditions**: Match one or more of the following conditions:
        - When the user specifies a particular item by its position, such as: "I like the first one," "I love the last dress," "Show me the 2nd item," etc.
        - When the user asks for your preference, such as: "Which one do you like?" or "Which one is the most...?"
        - When the user requests more details about a specific item, such as: "Show me more of the second item.", "I want to see the last item."
        - When the user describes the item they want, such as: "I want to see the red dress with a slit" or "I like the black dress."
        - When the user selects any item from the previously recommended fashion options.
        - When the user requests a close-up view again after reviewing the first or second set of images.
        """
        # Load the session data
        session_data = self._get_session_data()
        # Convert the session data to a dictionary if it is not already
        if not isinstance(session_data, dict):
            session_data = json.loads(session_data)  # type: ignore
        # Load chat history
        chat_history = self._get_chat_history()
        logger.info("Triggered get_close_up_images")
        logger.info(
            f"Previous user preferences: {session_data['prev_user_preferences']}"
        )
        logger.info(
            f'Initial Recommended Items: {session_data["recommended_items"]["recent"]}'
        )
        if session_data == []:
            return """Unfortunately, there are no fashion items that match the user's query. Please specify your preferences and try again."""

        # Ask GPT to identify the item that the user wants to see a close-up view of
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": """Based on the user's chat history, select the item that the user wants to see a close-up view of. For example, if the user says "Show me more of the first item", return the first item. If the user says """,
                },
                {
                    "role": "user",
                    "content": f"""Here is the chat history: "{chat_history}". Here is the user's query: "{query}". Here is the previously recommended fashion items: "{session_data["recommended_items"]["recent"]}". Select the item that the user wants to see a close-up view of and return the index of the item (starting from 0).""",
                },
            ],
            model="gpt-4o-2024-08-06",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "schema": CloseUpItem.model_json_schema(),
                },
            },
        )
        answer = chat_completion.choices[0].message.content
        if answer is None:
            logger.error("Failed to retrieve GPT response for past image identifier.")
            raise ValueError(
                "Failed to retrieve GPT response for past image identifier."
            )
        index = json.loads(answer)["index_of_item"]
        logger.info(f"Item Index: {index}")
        logger.info(
            f'Close up Image Results: {session_data["recommended_items"]["recent"][index]}'
        )

        # get the first three images
        result = {
            "item_names": [
                copy.deepcopy(
                    session_data["recommended_items"]["recent"][index]["title"]
                )
                * len(
                    session_data["recommended_items"]["recent"][index]["image_urls"][:4]
                )
            ],
            "images": copy.deepcopy(
                session_data["recommended_items"]["recent"][index]["image_urls"][:4]
            ),
        }
        if "spotlight" not in session_data:
            session_data["spotlight"] = []

        session_data["spotlight"] = [
            copy.deepcopy(session_data["recommended_items"]["recent"][index])
        ]
        session_data["spotlight"][0].pop("image_urls")
        logger.info(f"Close up Image Results: {result}")

        session_data["displayed_images"] = result

        # Update previous user preferences in the agent's session data
        target_item = session_data["recommended_items"]["recent"][index]
        session_data["prev_user_preferences"] = (
            f"color: {target_item['colors']}, item_name: {target_item['title']}, fit_features: {target_item['fit_features']}"
        )

        return f"""Return the following retrieved fashion item that the user selected: {session_data['spotlight']} exactly as it is. 
        In addition, persuade the user to purchase the item by highlighting its unique features with sales language.
        ### Examples of sales language:
        1. Affirmativeness: 
        - "You've got a good taste!"
        - "Fantastic choice!" 
        - "You can never go wrong with this one!"
        2. Exclusiveness: 
        - "This is a one-of-a-kind piece that you won't find anywhere else. It's designed to make you stand out."
        3. Confidence: 
        - "This is our best-selling item, and customers keep coming back for more because of its durability and timeless style." 
        4. Relatable: 
        - "I know how you feel. Finding the right fit is so important."
        - "This design has been getting rave reviews from customers just like you."
        5. Lifestyle appeal: 
        - "Imagine the compliments you'll receive in this elegant design."
        - "It's perfect for making an unforgettable impression."
        6. Quality assurance: 
        - "Crafted with high-quality materials, this piece offers both comfort and durability, ensuring it stays a favorite in your wardrobe."
        7. Emphasize value: 
        - "Invest in timeless style—this is a piece that will never go out of fashion."
        8. Limited Time Offer: 
        - "This is your chance to own a trendy piece that's only available for a limited time." 
        - "Don't miss out on something truly unique."
        - "Get it before it's gone!"
        9. Emphasizing Comfort: 
        - "With its breathable fabric and perfect fit, this piece will make you feel as amazing as you look."
        ###End of Examples###
        Chose the best sales language that fits the user's query and the item's features. If a phrase has been used in the past, try to use a different one.
        
        {self._generate_countdown_deal()}
"""

    # Rewrite the values for the RAG query
    def rewrite_colors(self, colors: List) -> str:
        return "Color(s): " + ", ".join(colors) if colors else ""

    def rewrite_fit_features(self, fit_features: List) -> str:
        return "Fit Feature(s): " + ", ".join(fit_features) if fit_features else ""

    def rewrite_occasions(self, occasions: List) -> str:
        return "Occasion(s): " + ", ".join(occasions) if occasions else ""

    @task(name="Retrieve Antonym of Disliked Fit Styles")
    def _retrieve_antonym_of_disliked_fit_styles(
        self, disliked_fit_styles: list, record_time: bool = True
    ) -> List:
        """
        Translates disliked fit styles into their preferred counterparts using GPT with few-shot examples.

        Args:
            disliked_fit_styles (list): A list of disliked fit styles (e.g., ["crop tops", "tight fit"]).

        Returns:
            dict: A dictionary with the original disliked fit styles as keys and their preferred counterparts as values.
        """

        start_time = time.time()

        if not disliked_fit_styles:
            if record_time:
                logger.info(
                    "Time taken to retrieve antonyms of disliked fit styles: "
                    + str(time.time() - start_time)
                )
            return []

        # Define the prompt with few-shot examples
        system_prompt = (
            "You are a fashion expert specializing in translating disliked fit styles into their preferred counterparts. "
            "For each provided disliked fit style, identify the most likely contrasting fit style that a user might prefer. "
            "Be specific and contextually accurate. Only provide alternatives that are realistic and meaningful in fashion."
            "Ensure a broad coverage of the opposite fit styles of the disliked fit styles to provide as many alternatives as possible."
        )

        few_shot_examples = """ "tight fit" can be translated to"loose fit, relaxed fit, oversized fit, etc."},
           "crop tops" can be translated to"longline tops, tunic tops, peplum tops, etc."},
           "long dress" can be translated to"short dress, mini dress, etc."},
           "short dress" can be translated to"long dress, maxi dress, etc."},
           "high slit" can be translated to"short slit, no slit, etc."},
           "short slit" can be translated to"high slit, long slit, etc."},
           "deep V neckline" can be translated to"shallow V neckline, high neckline, turtleneck, etc."},
           "baggy pants" can be translated to"slim-fit pants, tailored pants, etc."},
           "oversized jackets" can be translated to"tailored jackets, fitted jackets, etc."},
           "plunging neckline" can be translated to"high neckline, crew neckline, etc."},
           "wide-leg trousers" can be translated to"straight-leg trousers, slim-fit trousers, etc."},
        """

        user_prompt = (
            f"Disliked fit styles: {disliked_fit_styles}. Below are examples of translations for context:\n\n"
            f"{json.dumps(few_shot_examples, indent=2)}\n\n"
            f"Stricly provide the preferred counterparts for the given disliked fit styles in a dictionary that has the disliked fit styles as the only 1 key in the dictionary and their preferred counterparts as values which are in a list format. If there are no preferred fit styles for a disliked fit style, return None as the value. For example:\n\n"
            f"{{'translated_fit_style': [**list of preferred fit styles**]}}"
        )

        # Call GPT to process the antonyms
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model="gpt-4o-2024-08-06",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "fit_styles_translation",
                    "schema": AntonymsofNegativeFashion.model_json_schema(),
                },
            },
        )

        answer = chat_completion.choices[0].message.content
        if answer is None:
            logger.error("Failed to retrieve GPT response for preferred styles.")
            raise ValueError("Failed to retrieve GPT response for preferred styles.")
        try:
            # Process the response
            logger.info(
                f"Raw Antonyms of disliked fit styles: {chat_completion.choices[0].message.content}"
            )
            preferred_styles = json.loads(answer)
            # Normalize the output to ensure key conformation
            # lowercase the keys
            if "properties" in preferred_styles:
                preferred_styles = preferred_styles["properties"]
            preferred_styles = self.general_functions._lowercase_keys(preferred_styles)
            for key in preferred_styles:
                if preferred_styles[key] is not None:
                    if isinstance(preferred_styles[key], list):
                        preferred_styles[key] = [
                            i.lower() for i in preferred_styles[key]
                        ]
                    else:
                        try:
                            preferred_styles[key] = preferred_styles[key].lower()
                        except Exception as e:
                            logger.error(
                                f"Error converting {key} to lower case. Error: {e}"
                            )
                            logger.error(preferred_styles[key])
                            preferred_styles[key] = []

            # if the list is empty, replace it with None
            for key in preferred_styles:
                if (
                    isinstance(preferred_styles[key], list)
                    and len(preferred_styles[key]) == 0
                ):
                    preferred_styles[key] = None
            logger.info(
                f"Processed Antonyms of disliked fit styles: {preferred_styles}"
            )
            if record_time:
                logger.info(
                    "Time taken to retrieve antonyms of disliked fit styles: "
                    + str(time.time() - start_time)
                )
            return preferred_styles["translated_fit_style"]
        except json.JSONDecodeError:
            logger.error("Failed to parse GPT response for preferred styles.")
            return []

    @task(name="Past Image Identifier")
    def past_image_identifier(
        self, query: str, chat_history: List | str, record_time: bool = True
    ) -> int:
        start_time = time.time()
        prompt = f"""Based on the chat history query, and the image understandings of the past recommended items, identify the image that the user is referencing. Return the index of the image (starting from 0).
        
        For example, if the user says "I like the second item", return 1.
        
        If the user did not explicitly specify which item they are referencing, return the index of the item which is most likely to be the user's preference.
        
        Here is the chat history: "{chat_history}". 
        
        Here is the user's query: "{query}".
        """

        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt},
            ],
            model="gpt-4o-2024-08-06",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "schema": PastImageIdentifier.model_json_schema(),
                },
            },
        )

        answer = chat_completion.choices[0].message.content
        if answer is None:
            logger.error("Failed to retrieve GPT response for past image identifier.")
            raise ValueError(
                "Failed to retrieve GPT response for past image identifier."
            )

        answer = json.loads(answer)
        if record_time:
            logger.info(
                f"Time taken to identify the past image: {time.time() - start_time} seconds"
            )
        if "index_of_item" in answer:
            return int(answer["index_of_item"])
        else:
            return int(answer["properties"]["index_of_item"])

    @task(name="Process Positive and Negative Preferences Concurrently")
    def _process_positive_negative_preferences_concurrently(
        self,
        query: str,
        chat_history: list | str,
        past_recommendations: dict,
        prev_user_preferences: str | None,
        image_to_analyze: int,
        record_time: bool = True,
    ) -> tuple[dict, dict]:
        # Run the two core tasks in parallel
        with ThreadPoolExecutor() as executor:
            negative_intents_future = executor.submit(
                self.fashion_negative_intent_tools._detect_negative_intents,
                query=query,
                chat_history=chat_history,
                record_time=RECORD_TIME,
            )
            text_understanding_future = executor.submit(
                self.fashion_text_understanding_tools._text_understanding,
                chat_history=chat_history,
                query=query,
                past_recommendations=(
                    past_recommendations["recent"]
                    if past_recommendations is not None
                    and "recent" in past_recommendations
                    else []
                ),
                prev_user_preferences=prev_user_preferences,
                image_to_analyze=image_to_analyze,
                record_time=RECORD_TIME,
            )

            # Retrieve the results from both futures
            text_understanding = text_understanding_future.result()
            negative_intents = negative_intents_future.result()
            LLMObs.annotate(
                input_data="Analyzing user preferences ...", tags={"windsor": "test"}
            )
            return text_understanding, negative_intents

    @tool
    def _recommendation_logic(
        self,
        query: str,
        top_k: int = 3,
        num_redundant: int = 7,
        base64_generative_image: str | None = None,
        return_json: bool = False,
    ) -> str | List:
        f"""This function retrieves clothings, accesories, costumes information from the knowledge base based on the user's query and/or the image uploaded by the user. This function can access chat history and the image uploaded by the user and use it to retrieve similar fashion items from the knowledge base. 
Args:
    query (str): The exact content entered by the user. 
    top_k (int): The number of fashion items to return. Defaults to {top_k}. If the user does not specify the number of items to return, the function must return the top {top_k} fashion items.
Returns:
    retrieved fashion items from the knowledge base.

**Trigger Conditions:**
- When the user asks for:
    1. any clothing items/costumes.
    2. specific type of outfit or dress for events.
    3. ambiguos fashion advice but the chat history provides a context.
    4. items based on the user's query and the image uploaded by the user.
    5. items/clothings/costumes based on a specific occasion, specific occasion, category, or color.
- If the user's query does not specify the amount of fashion items to return, you must return the top {top_k} fashion items (i.e. set top_k={top_k}).
"""
        start_time = time.time()
        # Load the session data
        session_data = self._get_session_data()
        # Convert session_data to a dictionary if it is not already
        if not isinstance(session_data, dict):
            session_data = json.loads(session_data)  # type: ignore

        # Get the chat history
        chat_history = self._get_chat_history()
        ### TODO: Define the way to collect user query, chat history, and image uploaded by the user.
        chat_history = chat_history if chat_history else []
        query = query if query else ""

        ##### Ensure previously recommended items are not repeated #####
        filtered_items = []
        if len(chat_history) > 0:  # type: ignore
            filtered_items = self.fashion_session_data_tools._fetch_recommended_items(
                query=query, chat_history=chat_history, record_time=RECORD_TIME  # type: ignore
            )

        base64_generative_image = (
            base64_generative_image if base64_generative_image else ""
        )

        ##### Load previous user preferences and past recommendations #####
        prev_user_preferences = session_data.get("prev_user_preferences", None)
        past_recommendations = session_data.get("recommended_items", None)

        ##### Rewrite user query #####

        ### Image Understanding ###

        # Placeholder for image understanding
        image_understanding = None
        base64_image_input = None

        """
        0 means the image is from the uploaded image, 1 means the image is from the recommended items. 2 means no image.
        """
        image_to_analyze = self.fashion_image_understanding_tools._image_identifier(
            query=query, chat_history=chat_history, record_time=RECORD_TIME  # type: ignore
        )
        # See if the agent thinks the user is referencing an image from the past but there is no image from the past
        if (
            image_to_analyze == ImageIdentificationOutput.RECOMMENDED_ITEMS
            and "recommended_items" not in session_data
        ):
            # User is not referencing an image from the past
            image_to_analyze = ImageIdentificationOutput.NO_IMAGE

        ### TODO: Enable the agent to handle the cases where the user is referencing an uploaded image and a generated image

        # If the user is referencing an image from the past
        if image_to_analyze == ImageIdentificationOutput.RECOMMENDED_ITEMS:
            past_image_index = self.past_image_identifier(
                query=query, chat_history=chat_history, record_time=RECORD_TIME  # type: ignore
            )
            logger.info(f"Past image to analyze: {past_image_index}")

            try:
                image_url = session_data["recommended_items"]["recent_image_urls"][
                    image_to_analyze
                ]
            except IndexError:
                logger.error(f"Index {image_to_analyze} is out of range.")
                image_url = session_data["recommended_items"]["recent_image_urls"][0]

            base64_image_input = (
                self.fashion_image_understanding_tools._image_url_to_base64(image_url)
            )
            try:
                ### TODO: Adjust the code once segment_and_replace_background is implemented
                segmented_base_64 = self.fashion_image_understanding_tools.segment_and_replace_background(
                    base64_image_input
                )
                base64_image_input = (
                    segmented_base_64
                    if segmented_base_64 is not None
                    else base64_image_input
                )
            except Exception as e:
                logger.error(f"Error segmenting and replacing background: {e}")

            image_understanding = json.loads(
                (
                    self.fashion_image_understanding_tools._image_understanding(
                        base64_image_input, record_time=RECORD_TIME
                    )
                )
            )
            logger.info(
                f"Image understanding from past recommended items: \n{image_understanding}"
            )

        # If the user is referencing an uploaded image
        elif image_to_analyze == ImageIdentificationOutput.UPLOADED_IMAGE:
            # TODO: Discuss with the ENG team on how to store the uploaded image
            base64_image_input = session_data["base64_image"]
            image_understanding = json.loads(
                (
                    self.fashion_image_understanding_tools._image_understanding(
                        base64_image_input, record_time=RECORD_TIME
                    )
                )
            )
            logger.info(
                f"Image understanding from uploaded image: \n{image_understanding}"
            )

        ### Text Understanding ###
        text_understanding_start_time = time.time()
        text_understanding, negative_intents = (
            self._process_positive_negative_preferences_concurrently(
                query=query,
                chat_history=chat_history,  # type: ignore
                past_recommendations=past_recommendations,
                prev_user_preferences=prev_user_preferences,
                image_to_analyze=image_to_analyze,  # type: ignore
                record_time=RECORD_TIME,
            )
        )
        if RECORD_TIME:
            logger.info(
                f"Time taken to process positive and negative preferences: {time.time() - text_understanding_start_time} seconds"
            )
        ##### Identify negative intents #####
        antonyms_of_disliked_features = None
        input_to_dislikes_conversion = []
        if (
            "disliked_fit_style" in negative_intents
            and negative_intents["disliked_fit_style"]
        ):
            input_to_dislikes_conversion.extend(negative_intents["disliked_fit_style"])
        if "aesthetics" in negative_intents and negative_intents["aesthetics"]:
            input_to_dislikes_conversion.extend(negative_intents["aesthetics"])
        logger.info(f"Disliked features: {input_to_dislikes_conversion}")
        if input_to_dislikes_conversion != []:
            antonyms_of_disliked_features = (
                self._retrieve_antonym_of_disliked_fit_styles(
                    disliked_fit_styles=input_to_dislikes_conversion,
                    record_time=RECORD_TIME,
                )
            )
            logger.info(
                f"Anotnyms of disliked fit styles: {antonyms_of_disliked_features}"
            )

        ##### Identify positive intents #####
        text_understanding = self.general_functions._lowercase_keys(text_understanding)
        item_name = text_understanding["item_name"]
        fit_features = text_understanding["fit_features"]
        if antonyms_of_disliked_features is not None:
            fit_features = fit_features + antonyms_of_disliked_features
            text_understanding["fit_features"] = fit_features

        # check if fit features if a list, make it a list if not
        if not isinstance(fit_features, List) and not fit_features:
            fit_features = fit_features.split()

        occasions = text_understanding["occasions"]
        if isinstance(occasions, dict) and "enum" in occasions:
            occasions = occasions["enum"]
        if not isinstance(occasions, List):
            occasions = [occasions]

        categories = text_understanding["categories"]
        if not isinstance(categories, List):
            categories = [categories]

        colors = text_understanding["colors"]
        if not isinstance(colors, List):
            colors = [colors]

        if len(colors) > MAX_COLOR_AMBIGUITY:
            clarification = f"""Politely tell the user that in order to provide fashion recommendation, I need to clarify which one is his or her favourite colors: {colors}."""
            return clarification

        rag_query = (
            "\n".join(
                [
                    item_name,
                    self.rewrite_occasions(occasions),
                    self.rewrite_colors(colors),
                    self.rewrite_fit_features(fit_features),
                ]
            )
            if colors is not None
            and colors != "none"
            and "none" not in colors
            and colors != "not specified"
            else ", ".join([item_name, self.rewrite_fit_features(fit_features)])
        )

        ##### Conflict resolution #####
        conflicts = []
        if (
            image_to_analyze != ImageIdentificationOutput.NO_IMAGE
            and image_understanding is not None
        ):
            rephrase_query_answer = (
                self.fashion_conflict_resolution_tools._resolve_conflicts(
                    query,
                    image_understanding,
                    text_understanding,
                    chat_history,  # type: ignore
                    record_time=RECORD_TIME,
                )
            )
            # Extract the resolved values
            item_name = rephrase_query_answer["item_name"]
            fit_features = rephrase_query_answer["fit_features"]
            occasions = rephrase_query_answer["occasions"]
            colors = (
                rephrase_query_answer["colors"]
                if "none" not in rephrase_query_answer["colors"]
                else []
            )

            # Check if colors is a list, if not, make it a list
            if isinstance(colors, str):
                colors = [colors]

            # Compose rag queries
            rag_query = "\n ".join(
                [
                    item_name,
                    self.rewrite_occasions(occasions),
                    self.rewrite_colors(colors),
                    self.rewrite_fit_features(fit_features),
                ]
            )
            conflicts = [rephrase_query_answer["conflicting_features"]]

            occasions = rephrase_query_answer["occasions"]
            categories = rephrase_query_answer["categories"]

        ### Store the user's preference in the session data for future reference ###
        full_description = f"occasion:{occasions}. category:{categories}. color:{colors}. item_name:{item_name}. fit_features:{fit_features}"

        ##### Retrieve fashion items from the knowledge base #####
        # Ensure occasions is a list of strings
        if isinstance(occasions, list):
            occasions = [str(occasion) for occasion in occasions]
        else:
            occasions = [str(occasions)]

        filter = self.rag_search_filter_utils_tools._get_filters(
            occasions,
            categories,
            colors,
            filtered_items,  # type: ignore
            negative_intents=negative_intents,
        )

        if filter is None:
            filter = dict()

        results, scores = self.rag_search_filter_utils_tools._text2img_search(
            query_text=rag_query,
            rag_query_for_image_search="Name: "
            + item_name
            + "\n"
            + self.rewrite_fit_features(fit_features),
            top_k=top_k + num_redundant,
            filter=filter,
            base64_image=base64_image_input,
            conflicts=conflicts,
            record_time=RECORD_TIME,
        )

        # Filter out results with no image URLs
        results = [result for result in results if len(result["image_urls"]) > 0]

        ##### Relax filter #####
        if len(results) < top_k:
            results = self.rag_search_filter_utils_tools._relax_filters(
                query_text=rag_query,
                top_k=top_k + num_redundant,
                occasions=occasions,
                categories=categories,
                colors=colors,
                filtered_items=filtered_items,  # type: ignore
                negative_intents=negative_intents,
                record_time=RECORD_TIME,
            )

        ###### Reranking #####
        preference_used_for_reranking = f"item_name:{item_name}. category:{categories}. color:{colors}. occasion:{occasions}. fit_features:{fit_features}"

        if len(results) > top_k:
            logger.info(
                f"Results before reranking: {[result['title'] for result in results]}"
            )
            results = self.fashion_reranker_tools._reranking(
                items=results,
                positive_preference=preference_used_for_reranking,
                negative_intents=str(negative_intents),
                current_query=query,
                record_time=RECORD_TIME,
                fields_to_eval=["title", "colors", "fit_features", "sizes"],
            )
            logger.info(
                f"Results after reranking: {[result['title'] for result in results]}"
            )

        ##### Process and organize the results #####

        names = set()  # Tracks how many distinct items we've seen
        # TODO: Discuss with eng team how to send back the image urls
        image_urls = []
        item_names = []
        product_urls = []
        combined_labels = []

        # Fields we want to return in return_results
        return_fields = ["title", "colors", "fit_features", "sizes", "product_url"]

        try:
            for result in results:
                # --------- 1) Store information of current retrieved items for future reference (all returns up to top_k) --------- #
                # Once we've gathered 'top_k' distinct items, stop entirely
                if len(names) == top_k:
                    break

                # If this is a brand new item name, it contributes to our top_k count
                is_new_item = result["title"] not in names
                if is_new_item:
                    names.add(result["title"])
                else:
                    continue

                # --------- 2) Collect fields of interest for return_results --------- #
                combined_labels.append(
                    {
                        key: result[key]
                        for key in result
                        if key in return_fields and result[key] is not None
                    }
                )
                # Store information related to the image
                image_urls.append(result["image_urls"][0])
                item_names.append(result["title"])
                product_urls.append(result["product_url"])

            # Wrap images in a dict, matching your original structure
            images = {
                "images": image_urls,
                "item_names": item_names,
                "product_urls": product_urls,
            }

        except Exception as e:
            logger.error(f"Error storing image links and item names: {e}")
            # If anything fails, revert to empty placeholders
            images = {"images": [], "item_names": [], "product_urls": []}

            combined_labels = []

        logger.info(f"Images: {images}")

        # Store the user's preferences and the recommended items in the session data
        if self.ENABLE_SESSION_DATA:
            session_data["prev_user_preferences"] = full_description
            if "recommended_items" not in session_data:
                session_data["recommended_items"] = {
                    "recent": copy.deepcopy(combined_labels),
                    "all": combined_labels,
                }
            else:
                session_data["recommended_items"]["recent"] = copy.deepcopy(
                    combined_labels
                )
                # add the item_names to the front of the list
                logger.info(f"Combined Names Labels: {combined_labels}")
                session_data["recommended_items"]["all"] = (
                    combined_labels + session_data["recommended_items"]["all"]
                )

            session_data["displayed_images"] = images
            if "recommended_items" not in session_data:
                session_data["recommended_items"] = {}

            session_data["recommended_items"]["recent_image_urls"] = images.get(
                "images", []
            )

            # TODO: discuss with eng team whether we want to store session data
            # self._write_session_data(session_data)

        if RECORD_TIME:
            logger.info(
                "Final time taken to recommend items: " + str(time.time() - start_time)
            )
        if len(combined_labels) == 0:
            return """Unfortunately, there are no fashion items that match the user's query. Please try again with a different query."""

        logger.info(f"Return Results: {combined_labels}")

        LLMObs.annotate(
            input_data={"chat_history": chat_history, "query": query},
            output_data={"fashion_items": combined_labels, "image_urls": image_urls},
            tags={"windsor": "test"},
        )
        final_instructions = f"""Recommend all the following retrieved fashion items to the user : {combined_labels}. Present these items with an engaging and persuasive tone that highlights their unique appeal with respect to the conversation with the user. \n\nPlace the image urls exactly as they are in the following structure: <image_urls>{image_urls}</image_urls>. Do **not** modify, rephrase, or simplify any of the image urls in any way."""
        if return_json:
            return f"""Extract the fashion items and return them to the user in the exact JSON format as {combined_labels}. DO NOT modify, rephrase, or paraphrase any content within the JSON structure. Maintain the original formatting precisely.

Additionally, append an extra JSON object:
"agent_response": YOUR_RESPONSE_HERE

where YOUR_RESPONSE_HERE should be your response to the user, strictly adhering to the given instructions: {final_instructions}.

Ensure the final output remains a valid JSON array that includes both the list of items and the additional "agent_response" object. Do not alter the JSON keys or structure in any way."""
        return final_instructions
