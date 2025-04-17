import os

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.query_engine import BaseQueryEngine
from llama_index.core.response_synthesizers import (
    ResponseMode,
    get_response_synthesizer,
)
from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone

# TODO: Create a knowledge index for the toast agent
TOAST_AGENT_PINECONE_INDEX = "TBD"


def create_query_engine(namespace) -> BaseQueryEngine:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY environment variable is not set")

    try:
        pc = Pinecone(pinecone_api_key)
        pinecone_index = pc.Index(TOAST_AGENT_PINECONE_INDEX)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Pinecone: {str(e)}")

    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index, namespace=namespace
    )

    cohere_api_key = os.getenv("COHERE_API_KEY")
    if not cohere_api_key:
        raise ValueError("COHERE_API_KEY environment variable is not set")

    try:
        embed_model = CohereEmbedding(
            api_key=cohere_api_key,
            model_name="embed-english-v3.0",  # current v3 models support multimodal embeddings
        )
        # Only set global model if needed
        Settings.embed_model = embed_model
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Cohere embedding model: {str(e)}")

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=Settings.embed_model,
    )
    response_synthesizer = get_response_synthesizer(
        response_mode=ResponseMode.NO_TEXT,
    )

    # Create our basic query engine
    query_engine = index.as_query_engine(
        similarity_top_k=3,
        response_synthesizer=response_synthesizer,
        # Use the menu documents with ids for extraction
        filters=MetadataFilters(
            filters=[ExactMatchFilter(key="include_ids", value="True")]
        ),
    )

    return query_engine
