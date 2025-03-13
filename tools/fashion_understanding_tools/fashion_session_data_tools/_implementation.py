import json
import time
from typing import List

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI, OpenAI

from utils.log import logger


class FashionSessionDataTools:

    def __init__(self, client: OpenAI, client_async: AsyncOpenAI):
        # Initialize OpenAI
        self.client = client
        self.client_async = client_async

    @task
    def _fetch_recommended_items(
        self, query: str, chat_history: List | str, record_time: bool = True
    ) -> List[str] | None:
        """
        Fetches recommended items based on the user's query and chat history.

        Args:
            query (str): The user's query.
            chat_history (List | str): The chat history.
            record_time (bool, optional): Whether to record the time taken. Defaults to True.

        Returns:
            List[str]: A list of recommended item names.
        """
        start_time = time.time()
        instruction_prompt = f"""Your task is to identify item names that have been recommended to the user using the chat history and user query. We will exclude them from the recommendations to avoid redundant suggestions. Include all the recommended item names in the output list unless the user query specifically asks to include them. 

Chat history: {chat_history}

User query: {query}


Output Format:
```json
["item1", "item2", "item3",...]
```
"""

        # Call OpenAI to fetch recommended items
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "user", "content": instruction_prompt},
            ],
            model="gpt-4o-2024-08-06",
        )
        # Process and normalize the response content
        answer = chat_completion.choices[0].message.content
        if record_time:
            logger.info(
                f"Time taken to fetch recommended items: {time.time() - start_time} seconds"
            )
        if answer is None:
            raise ValueError("GPT failed to generate a response.")

        # Extract the list of recommended items between ```json``` tags
        answer = answer.split("```json")[1].split("```")[0].strip().replace("'", '"')
        answer = json.loads(answer)

        item_names = []
        for item_name in answer:
            item_names.append(item_name)

            # Sometimes the item name will be rephrased by the Agent. For example, Bonnie Satin A Line Dress -> Bonnie Satin A-Line Dress, but Jodi Tulle A-Line Dress stays the same.
            # we want to make sure that we exclude all possible variations of the item
            if "-" in item_name:
                item_names.append(item_name.replace("-", " "))

        LLMObs.annotate(
            output_data=answer,
            input_data={"query": query, "chat_history": chat_history},
            tags={"windsor": "test"},
        )
        logger.info(f"Excluded items identified from chat history: {answer}")

        return item_names
