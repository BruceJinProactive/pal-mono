import json
from os import getenv

import vertexai
from google.oauth2 import service_account
from openai import OpenAI, OpenAIError
from pinecone import Pinecone
from vertexai.vision_models import MultiModalEmbeddingModel

from ai.llm import _settings
from utils.log import logger
from utils.secret import get_client_secret

from .constant import SYSTEM_PROMPT, USER_PROMPT


class PineconeIntegration:
    def __init__(
        self,
        pinecone_api_key: str,
        pinecone_index_name: str,
        pinecone_namespace: str,
        pinecone_dim: int,
        vertexai_project_id: str,
        vertexai_location: str = "us-central1",
    ):
        # NOTE: Temporary use of vertex ai multimodal embedding model

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
            project=vertexai_project_id,
            location=vertexai_location,
            credentials=credentials,
        )
        self.emb_model = MultiModalEmbeddingModel.from_pretrained(
            "multimodalembedding@001"
        )

        # Pinecone
        pc_client = Pinecone(api_key=pinecone_api_key)
        self.index = pc_client.Index(name=pinecone_index_name)
        self.pinecone_dim = pinecone_dim
        self.pinecone_namespace = pinecone_namespace

        # OpenAI
        self.openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
        self.openai_model = _settings.ai_settings.gpt_4o_2024_08_06

    def retrieve_image_by_chat_history(
        self, chat_history: list[str], top_k: int = 3
    ) -> str:
        try:
            chat_completion = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": USER_PROMPT.format(chat_history=chat_history),
                    },
                ],
            )
        except OpenAIError as e:
            logger.error(
                f"Failed to query OpenAI with chat history '''{chat_history}'''\n{e}"
            )
            return "Failed to retrieve image. Query to OpenAI failed."

        img_rag_query = chat_completion.choices[0].message.content

        if img_rag_query is None:
            return "Failed to retrieve image. Error with extracting relevant information from chat history."

        logger.info(
            f"Retrieving image from Pinecone index...\nImage RAG Query:'{img_rag_query}'"
        )

        try:
            # NOTE: Temporary embedding strategy - using google vertex ai multimodal embedding
            query_embedding = self.emb_model.get_embeddings(
                contextual_text=img_rag_query, dimension=self.pinecone_dim
            )
        except Exception as e:
            logger.error(f"Failed to create embeddings: {e}")
            return "Failed to retrieve image. Error with creating embedding."

        try:
            query_response = self.index.query(
                namespace=self.pinecone_namespace,
                vector=query_embedding.text_embedding,
                top_k=top_k,
                include_values=False,
                include_metadata=True,
            )
        except Exception as e:
            logger.error(f"Failed to query Pinecone index: {e}")
            return "Failed to retrieve image. Error with query to Pinecone index."

        # Extract image URL from Pinecone matches
        matches = query_response["matches"]

        if not matches:
            return "Failed to retrieve image. No image found in Pinecone index."

        # TODO: update to return top 3
        image_url = matches[0]["metadata"]["image_url"]

        return image_url
