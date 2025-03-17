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


# TODO: This code is bad >:( Refactor once it works. (ToT)
def create_query_engine(namespace) -> BaseQueryEngine:
    pc = Pinecone(os.getenv("PINECONE_API_KEY"))
    pinecone_index = pc.Index("agents")

    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index, namespace=namespace
    )

    Settings.embed_model = CohereEmbedding(
        api_key=os.getenv("COHERE_API_KEY"),
        model_name="embed-english-v3.0",  # current v3 models support multimodal embeddings
    )

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
