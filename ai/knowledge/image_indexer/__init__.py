import json
import re
from os import getenv
from typing import Any

import requests
import vertexai
from google.oauth2 import service_account
from pinecone import Pinecone, ServerlessSpec, UpsertResponse
from vertexai.vision_models import Image, MultiModalEmbeddingModel

from utils.log import logger
from utils.secret import get_client_secret


class ShopifyImageIndexer:
    pinecone_index_name: str = "windsor-demo"
    vertexai_project_id: str = "imagerag-438322"
    vertexai_location: str = "us-central1"
    pinecone_api_key: str | None = getenv("PINECONE_API_KEY")

    def __init__(self):
        google_creds_str = get_client_secret("GOOGLE_APPLICATION_CREDENTIALS")
        google_creds_dict = json.loads(google_creds_str)

        # Ensure the private key has the correct format
        if "private_key" in google_creds_dict:
            google_creds_dict["private_key"] = google_creds_dict["private_key"].replace(
                "\\n", "\n"
            )

        credentials = service_account.Credentials.from_service_account_info(
            google_creds_dict
        )

        vertexai.init(
            project=self.vertexai_project_id,
            location=self.vertexai_location,
            credentials=credentials,
        )
        self.emb_model = MultiModalEmbeddingModel.from_pretrained(
            "multimodalembedding@001"
        )

        # Pinecone
        self.pc_client = Pinecone(self.pinecone_api_key)

        self.__create_index_if_not_exists(self.pinecone_index_name, dimension=1408)
        self.index = self.pc_client.Index(self.pinecone_index_name)

    def __load_image(self, image_url: str) -> Image:
        """Load and preprocess the image.

        Args:
            image_url (str): URL of the image to be loaded.

        Returns:
            Image: A Vertex AI Image object.
        """
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        return Image(response.content)

    def __get_embedding(
        self, image_url: str, embedding_data: dict[str, Any]
    ) -> list[float]:
        """Get embedding for image and metadata.

        Args:
            image_url (str): Item's image url.
            embedding_data (dict[str, Any]): Item's data to embed.

        Returns:
            list[float]: The cross-modality embedding.
        """

        if embedding_data.get("description"):
            # Remove HTML tags from body_html
            clean = re.compile("<.*?>")
            embedding_data["description"] = re.sub(
                clean, "", embedding_data["description"]
            )

        # Embed only title and body_html (description)
        metadata_str = ", ".join(
            str(v)
            for k, v in embedding_data.items()
            if k in ["title", "body_html"] and v is not None
        )

        # NOTE: We cut the metadata string to 1024 characters to avoid exceeding embedder limit
        metadata_str = metadata_str[:1024]

        if not image_url:
            # If item does not have an image, use only metadata for embedding

            multimodal_embedding = self.emb_model.get_embeddings(
                contextual_text=metadata_str,
                dimension=1408,
            )
            text_embedding = multimodal_embedding.text_embedding

            if not text_embedding:
                raise ValueError("Error with creating cross modality embedding.")

            cross_modality_embedding = text_embedding

        else:
            multimodal_embedding = self.emb_model.get_embeddings(
                image=self.__load_image(image_url),
                contextual_text=metadata_str,
                dimension=1408,
            )
            text_embedding = multimodal_embedding.text_embedding
            image_embedding = multimodal_embedding.image_embedding

            if not text_embedding or not image_embedding:
                raise ValueError("Error with creating cross modality embedding.")

            combined = [x + y for x, y in zip(text_embedding, image_embedding)]
            cross_modality_embedding = list(map(lambda x: x / 2, combined))

        return cross_modality_embedding

    def __create_index_if_not_exists(
        self, index_name: str, dimension: int = 1408
    ) -> None:
        """Create Pinecone index if it doesn't exist.

        Args:
            index_name (str): The name of the index.
            dimension (int, optional): The dimension of the index. Defaults to 1408.
        """
        try:
            self.pc_client.describe_index(index_name)
            logger.info(f"Index '{index_name}' already exists.")
        except Exception:
            logger.info(f"Index '{index_name}' does not exist. Creating...")
            self.pc_client.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            logger.info(f"Index '{index_name}' created successfully.")

    def upsert(
        self,
        item: dict[str, Any],
    ) -> UpsertResponse | None:
        """Upsert into Pinecone index.

        Args:
            item (dict[str, Any]): The item to upsert.

        Returns:
            UpsertResponse: The response from Pinecone after upsertion.
        """
        try:
            embedding = self.__get_embedding(item["image_url"], item["embedding_data"])

            upsert_response = self.index.upsert(
                vectors=[
                    {
                        "id": item["id"],
                        "values": embedding,
                        "metadata": item["metadata"],
                    }
                ],
                namespace="cross-modality-embeddings-full",
            )

            logger.info(
                f"Upserted embedding for item ID {item['id']}\n"
                f"Response: {upsert_response}\n"
                f"Item info: {item}"
            )

            return upsert_response
        except Exception as e:
            logger.error(f"Error upserting item to Pinecone: {e}\nItem: {item}")
            return None

    def batch_upsert(self, items: list[dict[str, Any]]) -> tuple[int, int]:
        """Upsert multiple items into Pinecone index.

        Args:
            items (list[dict[str, Any]]): The list of items to upsert.

        Returns:
            tuple[int, int]: A tuple containing the number of successful upsertions and the number of failed upsertions.
        """
        # TODO: Make this more efficient by batching upsertions

        failures = 0
        for item in items:
            try:
                self.upsert(item)

            except Exception as e:
                logger.error(f"Error upserting item to Pinecone: {e}\nItem: {item}")
                failures += 1
                continue

        logger.info("Pinecone upsertion complete.")

        successes = len(items) - failures
        return successes, failures
