import os
import time
from typing import List

import numpy as np
from agno.tools.toolkit import Toolkit
from openai import AsyncOpenAI, OpenAI

from utils.log import logger


class FashionRerankerTools(Toolkit):

    def __init__(self):
        super().__init__(name="fashion_reranker_tools")
        ### TODO: De-register this function as we don't want the agent to use it. We want to use it internally.
        self.register(self._reranking)
        # Initialize OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        ### TODO: Define the session data structure with ENG team
        # Placeholder for session data
        self.session_data = {}

    def _softmax(self, logits):
        exps = np.exp(
            logits - np.max(logits)
        )  # Shift by max(logits) for numerical stability
        return exps / np.sum(exps)

    def _reranking(
        self,
        items: List[dict],
        positive_preference: str,
        negative_intents: str,
        current_query: str,
        record_time: bool = True,
    ) -> List[dict]:
        logger.info(f"Positive preference for rerankning: {positive_preference}")
        logger.info(f"Negative intents for rerankning: {negative_intents}")

        start_time = time.time()

        input_to_reranking = []
        relevance_score = []
        for i in items:
            temp = {
                "title": i["title"],
                "colors": i["colors"],
                "product_type": i["product_type"],
                "fit_features": i["fit_features"],
            }
            input_to_reranking.append(temp)
            # Define the schema using Pydantic

            # Define the question
            reranking_prompt = f"""Your task is to determine if the following fashion item is relevant based on the user preference and the latest query, return True or False only.
            The given item contains title, color, description of features, and other information.
            You're given the user preference descriptions of what the user prefers and what the user dislikes.
            You're also given the user's latest query.
            You must pay special attention to the user query and user preference, and determine if the item is relevant based on the title, color, and description of features to see if they align with the user's preference or contain the user's dislikes.
            Here is the user's latest query: {current_query}. Here is the description of the features user prefers: {positive_preference}. The items that fit the user's query and contain (or resemble) the user's prefered features in their titles, colors, and descriptions of features are more relevant \n### Note: ignore the value "similar to the image" in the user preference, do not rank items based on this value.
            Here is the description of what user dislikes, the items that contain the follwoing features may not be as relevant: {negative_intents}
            Here is the item to be determined: {temp}."""

            # Query GPT-4o with logits enabled
            completion = self.client.chat.completions.create(
                model="gpt-4o-2024-08-06",  # Ensure you're using a model that supports logits
                messages=[
                    {
                        "role": "system",
                        "content": "You are a fashion expert specializing in determining the relevance of fashion items based on user preferences and queries. For each item, decide if it is relevant based on the user's preferences and the latest query. Return 'True' if the item is relevant and 'False' if it is not. Ensure your decision aligns with the user's preferences and dislikes.",
                    },
                    {"role": "user", "content": reranking_prompt},
                ],
                logprobs=True,  # Enable logits retrieval
                max_tokens=1,  # Expect a single token output for "True" or "False"
                temperature=0,  # Deterministic output
                top_logprobs=2,  # Retrieve the logits for top 2 tokens
            )

            answer = completion.choices[0].logprobs

            if answer is None or answer.content is None:
                raise ValueError("GPT failed to generate a response.")

            token_logprobs = answer.content[0].top_logprobs

            # Retrieve logits for "True" and "False"
            logits = {logprob.token: logprob.logprob for logprob in token_logprobs}

            # Ensure keys exist for "True" and "False" and default to -inf if missing
            true_logprob = logits.get("True", -np.inf)
            false_logprob = logits.get("False", -np.inf)

            # Prepare logits array
            logits_array = [true_logprob, false_logprob]
            probabilities = self._softmax(np.array(logits_array))
            relevance_score.append(probabilities[0])

        # rank the scores in the relevance_score list, maintain the order of the items
        sorted_scores = sorted(relevance_score, reverse=True)
        # Create a dictionary to store the rank of each score
        rank_dict = {score: rank + 1 for rank, score in enumerate(sorted_scores)}
        # Map the ranks back to the original order of scores
        ranked_scores = [rank_dict[score] for score in relevance_score]

        if record_time:
            logger.info("Time taken to rerank items: " + str(time.time() - start_time))

        reranked_items = [
            item for _, item in sorted(zip(ranked_scores, items), key=lambda x: x[0])
        ]

        return reranked_items
