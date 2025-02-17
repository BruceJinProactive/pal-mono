import base64
import io
import os
import time
from typing import Any, List

import numpy as np
from agno.tools.toolkit import Toolkit
from classes import GeneralFunctions
from openai import AsyncOpenAI, OpenAI
from PIL import Image
from pinecone import Pinecone

from utils.log import logger

general_functions = GeneralFunctions()
hierarchy = general_functions.get_hierarchy()


class FashionRagSearchFilterUtilsTools(Toolkit):

    def __init__(self):
        super().__init__(name="fashion_rag_search_tools")
        ### TODO: De-register this function as we don't want the agent to use it. We want to use it internally.
        self.register(self._text2img_search)
        # Initialize OpenAI
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        ### TODO: Define the session data structure with ENG team
        # Placeholder for session data
        self.session_data = {}

        # Initialize Pinecone
        pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
        index_name = "windsor-demo-2-1"
        self.pc_index = pc.Index(index_name)
        self.pinecone_namespace = "cross-modality-embeddings-full"
        self.pinecone_dim = 1408

    ### TODO: Implement the text embedding retriever
    def _get_text_embedding(
        self, text: str, GOOGLE_VERTEX: bool = False
    ) -> List[float]:
        """
        Get the text embedding from OpenAI

        text: str
        GOOGLE_VERTEX: bool

        Returns:
        List: a list of floats representing the text embedding
        """
        return [0.0] * 512

    ### TODO: Implement the image embedding retriever
    def _get_image_embedding(
        self, image_data: Image.Image, GOOGLE_VERTEX=False
    ) -> List[float]:
        """Get embedding for the image."""

        return [0.0] * 512

    def decode_image(self, base64_image: str) -> Image.Image:
        """Decode the base64 image."""
        image_data = base64.b64decode(base64_image)
        image = Image.open(io.BytesIO(image_data))

        return image

    def _text2img_search(
        self,
        query_text,
        top_k=5,
        filter: dict | None = None,
        base64_image: str | None = None,
        rag_query_for_image_search: str | None = None,
        conflicts: List[dict] | List = [],
    ) -> tuple[List[dict], List[Any]]:
        """
        Based on the user's query, search for the most relevant items in the pinecone database.

        query_text: str
        top_k: int

        Returns:
        List: a List of dictionaries with the metadata of the records rerieved
        """
        start_time = time.time()

        # Get the text embedding
        logger.info(f"Query Text: {query_text}")
        if isinstance(query_text, list):
            query_embedding = [
                self._get_text_embedding(text, GOOGLE_VERTEX=True)
                for text in query_text
            ]
            query_embedding = np.average(query_embedding, axis=0).tolist()
        else:
            query_embedding = self._get_text_embedding(query_text, GOOGLE_VERTEX=True)

        def get_positive_negative_embeddings(conflicts):
            negative_embeddings, positive_embeddings = [], []
            for conflict in conflicts:
                # Remove all none occurrences
                conflict["user"] = [
                    i
                    for i in conflict.get("user", [])
                    if i is not None and i.lower() != "none"
                ]
                conflict["image"] = [
                    i
                    for i in conflict.get("image", [])
                    if i is not None and i.lower() != "none"
                ]

                logger.info(f"Resolving conflict through embeddings: {conflict}")
                # Check if the conflict is empty
                if len(conflict["user"]) == 0 or len(conflict["image"]) == 0:
                    continue

                # concatenate the image's colors
                negative_embeddings.append(
                    self._get_text_embedding(
                        ", ".join(conflict["image"]), GOOGLE_VERTEX=True
                    )
                )
                positive_embeddings.append(
                    self._get_text_embedding(
                        ", ".join(conflict["user"]), GOOGLE_VERTEX=True
                    )
                )

            if len(negative_embeddings) == 0 or len(positive_embeddings) == 0:
                return None, None
            else:
                # Average the embeddings
                negative_embeddings = np.average(negative_embeddings, axis=0)
                positive_embeddings = np.average(positive_embeddings, axis=0)

                return positive_embeddings, negative_embeddings

        if base64_image is not None:
            # Check if the image embeddings are already in the session data
            if (
                "image_embeddings"
                not in self.session_data["image_understandings_memory"][base64_image]
            ):
                image_embedding = self._get_image_embedding(
                    self.decode_image(base64_image)
                )
                # update the image embeddings in the session data
                self.session_data["image_understandings_memory"][base64_image][
                    "image_embeddings"
                ] = image_embedding
            else:
                logger.info("Using the image embeddings from the session data")
                image_embedding = self.session_data["image_understandings_memory"][
                    base64_image
                ]["image_embeddings"]

            if len(conflicts) > 0:
                positive_embeddings, negative_embeddings = (
                    get_positive_negative_embeddings(conflicts)
                )

                if negative_embeddings is None or positive_embeddings is None:
                    if rag_query_for_image_search is not None:
                        query_embedding = (
                            np.array(
                                self._get_text_embedding(rag_query_for_image_search)
                            )
                            + np.array(image_embedding)
                        ) / 2
                    else:
                        query_embedding = np.array(image_embedding)
                else:
                    # Calculate the new query embedding
                    if rag_query_for_image_search is not None:
                        query_embedding = (
                            np.array(
                                self._get_text_embedding(rag_query_for_image_search)
                            )
                            + np.array(image_embedding)
                            + np.array(positive_embeddings)
                            - np.array(negative_embeddings)
                        ) / 2
                    else:
                        query_embedding = (
                            np.array(image_embedding)
                            + np.array(positive_embeddings)
                            - np.array(negative_embeddings)
                        )

                query_embedding = query_embedding.tolist()

        elif len(conflicts) > 0:
            # turn the conflict in to a string with new line characters separating the keys
            positive_embeddings, negative_embeddings = get_positive_negative_embeddings(
                conflicts
            )
            query_embedding = (
                np.array(query_embedding)
                + np.array(positive_embeddings)
                - np.array(negative_embeddings)
            )

            query_embedding = query_embedding.tolist()
        # Query Pinecone
        query_response = self.pc_index.query(
            namespace=self.pinecone_namespace,
            vector=query_embedding,
            top_k=top_k,
            include_values=False,
            include_metadata=True,
            filter=filter,
        )
        res = query_response["matches"]
        results = [i["metadata"] for i in res]
        scores = [i["score"] for i in res]
        logger.info(f"Scores: {scores}")
        logger.info(f"Time taken to query Pinecone: {time.time() - start_time}")
        return results, scores

    def _get_filters(
        self,
        occasions: List[str],
        categories: List[str],
        colors: List[str],
        filtered_items: List[str],
        release_criteria: List[str] | None = None,
        negative_intents: dict | None = None,
    ) -> dict:
        """This function extracts the filters from a user's query based on the best occasion, specific occasion, and category of outfit for the user, while also applying any negative intents.

        Args:
            occasions (List): The best occasion for the user.
            categories (List): The category of outfit for the user.
            colors (List): The color of the outfit for the user.
            release_criteria (List): Criteria to release filters in a specific order (e.g., ['occasion', 'category', 'color']).
            negative_intents (dict): Attributes to exclude based on detected negative intents.

        Returns:
            dict: A dictionary of filters extracted from the user's query.
        """
        and_conditions = []

        final_product_types = []
        final_tags = []
        final_product_types_tags = []
        final_colors = []

        # Apply negative intent filters by setting "$exists": False
        if negative_intents:
            for key, values in negative_intents.items():
                # Skip empty values
                if values is None or len(values) == 0:
                    continue
                if not isinstance(values, list) and str(values).lower() == "null":
                    values = []

                # Exclude the specified values from the filter
                if key == "color":
                    and_conditions.append({"colors": {"$nin": values}})
                else:
                    and_conditions.append({"tags": {"$nin": values}})
        # Apply positive filtering conditions, omitting any criteria specified in release_criteria
        if (
            (release_criteria is None or "occasion" not in release_criteria)
            and occasions
            and occasions[0] != "none"
            and occasions != "none"
        ):
            for occasion in occasions:
                occasion = occasion.lower()
                if (
                    occasion not in hierarchy["occasions"]
                    or occasion == "similar to the image"
                ):
                    logger.error(f"Invalid occasion: {occasion}")
                    continue
                if occasion != "none" and occasion != "others":
                    final_tags.append(occasion)

        if (
            (release_criteria is None or "category" not in release_criteria)
            and categories
            and categories[0] != "none"
            and categories[0] != "general outfits"
            and categories != "none"
        ):
            for category in categories:
                category = category.lower()
                if (
                    category not in hierarchy["categories"]
                    or category == "similar to the image"
                ):
                    logger.error(f"Invalid category: {category}")
                    continue
                if category != "none":
                    if category == "mini dresses":
                        if "dresses" not in final_product_types_tags:
                            final_product_types_tags.append("dresses")
                        final_tags.append("mini")
                    elif category == "belts":
                        final_product_types.append(category)
                    else:
                        if category not in final_product_types_tags:
                            final_product_types_tags.append(category)

        if (
            (release_criteria is None or "color" not in release_criteria)
            and colors
            and colors[0] != "none"
            and colors != "none"
        ):
            for color in colors:
                color = color.lower()
                if color not in hierarchy["colors"] or color == "similar to the image":
                    logger.error(f"Invalid color: {color}")
                    continue
                if color != "none":
                    final_colors.append(color)

        # Construct the final filter
        if len(final_tags) > 0:
            and_conditions.append({"tags": {"$in": final_tags}})

        if len(final_product_types_tags) > 0:
            and_conditions.append({"tags": {"$in": final_product_types_tags}})

        if len(final_product_types) > 0:
            and_conditions.append({"product_type": {"$in": final_product_types}})

        if len(final_colors) > 0:
            and_conditions.append({"colors": {"$in": final_colors}})

        # Exclude previously recommended items
        if filtered_items:
            and_conditions.append({"title": {"$nin": filtered_items}})

        logger.info(f"and_conditions: {and_conditions}")

        filter = {"$and": []}
        if and_conditions:
            filter["$and"] = and_conditions

        result = {}
        result["filter"] = filter if filter else None

        return result

    def _relax_filters(
        self,
        query_text: str,
        top_k: int,
        occasions: List[str],
        categories: List[str],
        colors: List[str],
        filtered_items: List[str],
        negative_intents: dict | None = None,
    ) -> List:
        """
        Gradually release filter criteria in the order: occasion -> category -> color,
        and accumulate results until the required number of results is reached.

        Args:
            query_text (str): The original query text for the search.
            top_k (int): Number of results to return.
            occasions (List): List of occasion filters.
            categories (List): List of category filters.
            colors (List): List of color filters.
            filtered_items (List): List of items to exclude.
            required_results (int): Minimum number of required results.

        Returns:
            List: A List of retrieved items that match the relaxed filters.
        """
        logger.info(
            f"Relaxing filters to retrieve more results, required results: {top_k}, current results: {len(filtered_items)}"
        )

        release_order = ["occasion", "category", "color"]
        logger.info(
            f"Original Criterias: occasions: {occasions}, categories: {categories}, colors: {colors}"
        )
        accumulated_results = []

        for i in range(len(release_order) + 1):
            release_criteria = release_order[:i]
            filter_criteria = self._get_filters(
                occasions,
                categories,
                colors,
                filtered_items,
                release_criteria=release_criteria,
                negative_intents=negative_intents,
            )["filter"]

            results, scores = self._text2img_search(
                query_text=query_text, top_k=top_k, filter=filter_criteria
            )

            # Accumulate unique results to avoid duplicates
            new_results = [item for item in results if item not in accumulated_results]
            accumulated_results.extend(new_results)

            logger.info(
                f"Relaxed filters: {release_criteria}, accumulated results: {len(accumulated_results)}"
            )

            # Check if we have enough results after this relaxation step
            if len(accumulated_results) >= top_k:
                return accumulated_results

        # If we exit the loop without meeting the required results, return all accumulated results
        return accumulated_results
