import json
import re
from os import getenv
from typing import Any
import time

import requests
import shopify
import vertexai
from google.oauth2 import service_account
from pinecone import Pinecone, ServerlessSpec, UpsertResponse
from vertexai.vision_models import Image, MultiModalEmbeddingModel

from utils.log import logger
from utils.secret import get_client_secret

from collections import defaultdict


class ShopifyImageIndexer:
    pinecone_index_name: str = "windsor-demo"
    vertexai_project_id: str = "imagerag-438322"
    vertexai_location: str = "us-central1"
    pinecone_api_key: str | None = getenv("PINECONE_API_KEY")
    unique_labels: dict[str, set[str]] = defaultdict(set)

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

    def __get_embedding(self, image_url: str, metadata: dict[str, Any]) -> list[float]:
        """Get embedding for image and metadata.

        Args:
            image_url (str): Product's image url.
            metadata (dict[str, Any]): Product's metadata.

        Returns:
            list[float]: The cross-modality embedding.
        """

        # Embed only title and fit_features (description)
        metadata_str = ", ".join(
            str(v)
            for k, v in metadata.items()
            if k in ["title", "fit_features"] and v is not None
        )

        # NOTE: We cut the metadata string to 1024 characters to avoid exceeding embedder limit
        metadata_str = metadata_str[:1024]

        if not image_url:
            # If product does not have an image, use only metadata for embedding

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

    def _upsert(self, product: dict[str, Any]) -> bool:
        """Upsert into Pinecone index.

        Args:
            product (dict[str, Any]): The product to upsert.

        Returns:
            bool: True if the product was successfully upserted, False otherwise.
        """
        try:
            embedding = self.__get_embedding(product["image_url"], product["metadata"])

            upsert_response = self.index.upsert(
                vectors=[
                    {
                        "id": product["id"],
                        "values": embedding,
                        "metadata": product["metadata"],
                    }
                ],
                namespace="cross-modality-embeddings-full",
            )

            logger.info(
                f"Upserted embedding for product ID {product['id']}\n"
                f"Response: {upsert_response}\n"
                f"Product info: {product}\n"
            )

            return True
        except Exception as e:
            logger.error(
                f"Error upserting product to Pinecone: {e}\nProduct: {product}"
            )
            return False

    def __check_product_url(self, url: str) -> bool:
        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            if response.status_code == 200:
                logger.info(
                    f"URL is valid: {url} (Status Code: {response.status_code})"
                )
                return True
            elif response.status_code == 404:
                logger.error(f"URL not found (404): {url}")
            else:
                logger.error(f"URL returned status code {response.status_code}: {url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking URL {url}: {e}")

        return False

    def process_product(self, product: shopify.Product, max_retries: int = 5) -> bool:
        """Process a product and upsert it into Pinecone index.

        Args:
            product (shopify.Product): The product to process.

        Returns:
            bool: True if the product was successfully upserted, False otherwise.
        """
        metadata = product.attributes

        image_url = metadata["image"].attributes["src"] if metadata["image"] else ""

        ###
        # Create filtered metadata
        # Includes:
        # - product_url (if doesn't exist, skip indexing product)
        # - product_type
        # - tags
        # - options (colors and sizes)
        # - image_urls
        # - title
        # - body_html as fit_features
        # ###
        filtered_metadata = {}

        if metadata.get("handle"):
            windsor_product_url_prefix = "https://www.windsorstore.com/products/"
            product_url = windsor_product_url_prefix + metadata["handle"]
            valid = self.__check_product_url(product_url)

            if valid:
                filtered_metadata["product_url"] = product_url
            else:
                # NOTE: If the product does not have a valid URL, skip indexing it entirely
                logger.error(f"Product does not have a valid URL: {product_url}")
                return False

        # Format product type in metadata
        if metadata.get("product_type"):
            label = metadata["product_type"].strip().lower()
            filtered_metadata[label] = True
            self.unique_labels["product_type"].add(label)

        # Format tags in metadata
        if metadata.get("tags"):
            for tag in metadata["tags"].split(","):
                tag = tag.replace("[", "")
                tag = tag.replace("]", "")
                tag = tag.strip().lower()
                filtered_metadata[tag] = True
                self.unique_labels["tags"].add(tag)

        # Format options in metadata
        if metadata.get("options"):
            for option_object in metadata["options"]:
                option = option_object.attributes
                if option["name"] == "Color":
                    for color in option["values"]:
                        color = color.strip().lower()
                        filtered_metadata[color] = True
                        self.unique_labels["color"].add(color)
                elif option["name"] == "Size":
                    for size in option["values"]:
                        size = size.strip().lower()
                        filtered_metadata[size] = True
                        self.unique_labels["size"].add(size)

        # Format image urls in metadata
        if metadata.get("images"):
            image_urls: list[str] = []
            for image in metadata["images"]:
                image_urls.append(image.attributes["src"])
            filtered_metadata["image_urls"] = image_urls

        # Format title in metadata
        if metadata.get("title"):
            filtered_metadata["title"] = metadata["title"].strip()

        # Format fit features in metadata
        if metadata.get("body_html"):
            # Remove HTML tags from body_html
            clean = re.compile("<.*?>")
            filtered_metadata["fit_features"] = re.sub(clean, "", metadata["body_html"])

        product_data = {
            "id": str(metadata["id"]),
            "image_url": image_url,
            "metadata": filtered_metadata,
        }

        retries = 0
        while retries < max_retries:
            try:
                result = self._upsert(product_data)
                return result
            except Exception as e:
                logger.error(
                    f"Unexpected error with upserting product: {e}\n"
                    f"Product:{product_data}"
                )

            retries += 1
            if retries < max_retries:
                logger.info(f"[{retries+1}/{max_retries}] Retrying request...")
                time.sleep(2**retries)  # Exponential backoff
            else:
                logger.info("Max retries exceeded. Exiting.")
                break

        return False
