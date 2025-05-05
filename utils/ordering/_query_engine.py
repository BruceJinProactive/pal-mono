import os

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.query_engine import BaseQueryEngine
from llama_index.core.response_synthesizers import (
    ResponseMode,
    get_response_synthesizer,
)
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Index as PineconeIndex
from pinecone import Pinecone

from utils.log import logger


class QueryEngineConfig:
    """Configuration for query engine dependencies."""

    PINECONE_INDEX_NAME = "sandbox"
    COHERE_MODEL_NAME = "embed-english-v3.0"
    SIMILARITY_TOP_K = 3

    @staticmethod
    def get_pinecone_api_key() -> str:
        """Retrieve and validate Pinecone API key."""
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY environment variable not set")
        return api_key

    @staticmethod
    def get_cohere_api_key() -> str:
        """Retrieve and validate Cohere API key."""
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY environment variable not set")
        return api_key


def _initialize_pinecone_index(api_key: str) -> PineconeIndex:
    """Initialize and return Pinecone index."""
    try:
        pc = Pinecone(api_key=api_key)
        index = pc.Index(QueryEngineConfig.PINECONE_INDEX_NAME)
        logger.debug(
            f"Connected to Pinecone index: {QueryEngineConfig.PINECONE_INDEX_NAME}"
        )
        return index
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone index: {e}")
        raise


def create_query_engine(namespace: str) -> BaseQueryEngine:
    """Create and configure a query engine for the given namespace.

    Args:
        namespace (str): The namespace for the Pinecone vector store.

    Returns:
        BaseQueryEngine: Configured query engine.

    Raises:
        ValueError: If environment variables are missing or invalid.
        Exception: For Pinecone or Cohere initialization failures.
    """
    try:
        # Validate namespace
        if not namespace or not isinstance(namespace, str):
            raise ValueError("Namespace must be a non-empty string")

        # Initialize Pinecone
        pinecone_api_key = QueryEngineConfig.get_pinecone_api_key()
        pinecone_index = _initialize_pinecone_index(pinecone_api_key)
        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=namespace
        )

        # Configure embedding model
        cohere_api_key = QueryEngineConfig.get_cohere_api_key()
        Settings.embed_model = CohereEmbedding(
            api_key=cohere_api_key,
            model_name=QueryEngineConfig.COHERE_MODEL_NAME,
        )
        logger.debug(
            f"Initialized Cohere embedding model: {QueryEngineConfig.COHERE_MODEL_NAME}"
        )

        # Create vector store index
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=Settings.embed_model,
        )

        # Configure response synthesizer
        response_synthesizer = get_response_synthesizer(
            response_mode=ResponseMode.NO_TEXT
        )

        # Create query engine
        query_engine = index.as_query_engine(
            similarity_top_k=QueryEngineConfig.SIMILARITY_TOP_K,
            response_synthesizer=response_synthesizer,
        )
        logger.debug(f"Query engine created for namespace: {namespace}")

        return query_engine

    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
        raise
    except Exception as e:
        logger.error(f"Failed to create query engine: {e}")
        raise
