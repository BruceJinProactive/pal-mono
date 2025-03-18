import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import numpy as np
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI, OpenAI

from utils.log import logger


class FashionRerankerTools:

    def __init__(self, client: OpenAI, client_async: AsyncOpenAI):
        # Initialize OpenAI
        self.client = client
        self.client_async = client_async

    def _softmax(self, logits):
        exps = np.exp(
            logits - np.max(logits)
        )  # Shift by max(logits) for numerical stability
        return exps / np.sum(exps)

    def _fetch_item_relevance(
        self,
        item: Dict[str, Any],
        positive_preference: str,
        negative_intents: str,
        current_query: str,
        fields_to_eval: list[str],
        record_time: bool = True,
    ) -> float:
        """
        Helper method that does the actual GPT-based relevance check for a single item.
        Returns a float representing the probability that the item is relevant.
        """
        start_time = time.time()

        temp = {str(field): item.get(field, "") for field in fields_to_eval}
        # Build the prompt
        reranking_prompt = f"""Your task is to determine whether a given fashion item is relevant based on the user's preferences and latest query.

Return 'True' if the item is relevant and 'False' if it is not. Return True or False only.

The given fashion item includes details such as its title, color, description of features, and other information.

You're provided with the user preferences (what they like and dislike) and their latest query.
You must pay special attention to the user query and user preference, and determine relevance by checking if the title, color, and description align with the user's likes and avoid their dislikes.

User's Latest Query: {current_query}

User's Preferred Features: {positive_preference}

Items that match the user's query and include (or closely resemble) the user's preferred features in their title, color, and feature descriptions are considered more relevant.

Note: 
Ignore the value "similar to the image" in the user preference—do not evaluate items based on this criterion.

Items containing the following disliked features are considered less relevant: {negative_intents}.

Here is the item to be determined: {temp}.
"""

        # Synchronous GPT query
        completion = self.client.chat.completions.create(
            model="gpt-4o-2024-08-06",  # Ensure the model supports logprobs
            messages=[
                {"role": "user", "content": reranking_prompt},
            ],
            logprobs=True,
            max_completion_tokens=1,
            temperature=0,
            top_logprobs=2,
        )

        answer = completion.choices[0].logprobs
        end_time = time.time()
        if answer is None or answer.content is None:
            logger.error("GPT failed to generate a response for reranker.")
            raise ValueError("GPT failed to generate a response.")

        token_logprobs = answer.content[0].top_logprobs
        logits_dict = {lp.token: lp.logprob for lp in token_logprobs}
        true_logprob = logits_dict.get("True", -np.inf)
        false_logprob = logits_dict.get("False", -np.inf)

        probabilities = self._softmax(np.array([true_logprob, false_logprob]))
        logger.info(
            f"Item {item['title']}. Probabilities: {probabilities[0]}. True Logprob: {true_logprob}. False Logprob: {false_logprob}"
        )
        if record_time:
            logger.info(
                f"Time taken to fetch relevance for item {item['title']}: {end_time - start_time}. "
            )

        return probabilities[0]  # Probability that the item is "True"

    @task(name="Reranking")
    def _reranking(
        self,
        items: List[dict],
        positive_preference: str,
        negative_intents: str,
        current_query: str,
        fields_to_eval: list[str],
        record_time: bool = True,
        max_workers: int | None = None,
    ) -> List[dict]:
        """
        Synchronous method that uses a ThreadPoolExecutor internally to process
        each item in parallel.
        """
        logger.info(f"Positive preference for reranking: {positive_preference}")
        logger.info(f"Negative intents for reranking: {negative_intents}")

        start_time = time.time()

        # Prepare a container for results
        futures_map = {}
        relevance_scores = [0.0] * len(items)

        # Create a ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks for all items
            for idx, item in enumerate(items):
                future = executor.submit(
                    self._fetch_item_relevance,
                    item,
                    positive_preference,
                    negative_intents,
                    current_query,
                    fields_to_eval,
                    record_time,
                )
                futures_map[future] = idx

            # As each future completes, store the result in order
            for future in as_completed(futures_map):
                idx = futures_map[future]
                try:
                    result = future.result()
                    relevance_scores[idx] = result
                except Exception as e:
                    logger.error(f"Error processing item indexed {idx}: {e}")

        # Use argsort to get the indices of the sorted scores
        sorted_indices = np.argsort(relevance_scores)[::-1]

        # Reconstruct items in order of rank
        reranked_items = [items[i] for i in sorted_indices]

        if record_time:
            logger.info("Time taken to rerank items: " + str(time.time() - start_time))

        LLMObs.annotate(
            input_data={
                "items": items,
                "positive_preference": positive_preference,
                "negative_intents": negative_intents,
                "current_query": current_query,
            },
            output_data={"reranked_items": reranked_items},
            tags={"windsor": "test"},
        )
        return reranked_items
