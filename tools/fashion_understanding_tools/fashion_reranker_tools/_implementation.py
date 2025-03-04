import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import numpy as np
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
    ) -> float:
        """
        Helper method that does the actual GPT-based relevance check for a single item.
        Returns a float representing the probability that the item is relevant.
        """
        temp = {
            "title": item["title"],
            "colors": item["colors"],
            "product_type": item["product_type"],
            "fit_features": item["fit_features"],
        }

        # Build the prompt
        reranking_prompt = f"""Your task is to determine if the following fashion item is relevant based on the user preference and the latest query, return True or False only.
        The given item contains title, color, description of features, and other information.
        You're given the user preference descriptions of what the user prefers and what the user dislikes.
        You're also given the user's latest query.
        You must pay special attention to the user query and user preference, and determine if the item is relevant based on the title, color, and description of features to see if they align with the user's preference or contain the user's dislikes.
        Here is the user's latest query: {current_query}. Here is the description of the features user prefers: {positive_preference}. The items that fit the user's query and contain (or resemble) the user's prefered features in their titles, colors, and descriptions of features are more relevant \n### Note: ignore the value "similar to the image" in the user preference, do not rank items based on this value.
        Here is the description of what user dislikes, the items that contain the follwoing features may not be as relevant: {negative_intents}
        Here is the item to be determined: {temp}."""

        # Synchronous GPT query
        completion = self.client.chat.completions.create(
            model="gpt-4o-2024-08-06",  # Ensure the model supports logprobs
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a fashion expert specializing in determining the relevance of "
                        "fashion items based on user preferences and queries. For each item, "
                        "decide if it is relevant based on the user's preferences and the latest "
                        "query. Return 'True' if the item is relevant and 'False' if it is not. "
                        "Ensure your decision aligns with the user's preferences and dislikes."
                    ),
                },
                {"role": "user", "content": reranking_prompt},
            ],
            logprobs=True,
            max_tokens=1,
            temperature=0,
            top_logprobs=2,
        )

        answer = completion.choices[0].logprobs
        if answer is None or answer.content is None:
            raise ValueError("GPT failed to generate a response.")

        token_logprobs = answer.content[0].top_logprobs
        logits_dict = {lp.token: lp.logprob for lp in token_logprobs}
        true_logprob = logits_dict.get("True", -np.inf)
        false_logprob = logits_dict.get("False", -np.inf)

        probabilities = self._softmax(np.array([true_logprob, false_logprob]))
        return probabilities[0]  # Probability that the item is "True"

    def _reranking(
        self,
        items: List[dict],
        positive_preference: str,
        negative_intents: str,
        current_query: str,
        record_time: bool = True,
        max_workers: int = 5,
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

        # Now we have relevance_scores in the same order as `items`
        sorted_scores = sorted(relevance_scores, reverse=True)
        rank_dict = {score: rank + 1 for rank, score in enumerate(sorted_scores)}
        ranked_scores = [rank_dict[score] for score in relevance_scores]

        if record_time:
            logger.info("Time taken to rerank items: " + str(time.time() - start_time))

        # Reconstruct items in order of rank
        reranked_items = [
            item for _, item in sorted(zip(ranked_scores, items), key=lambda x: x[0])
        ]
        return reranked_items
