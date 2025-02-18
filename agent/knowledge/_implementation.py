import os

from llama_index.core import Settings, VectorStoreIndex, get_response_synthesizer
from llama_index.core.indices import MultiModalVectorStoreIndex
from llama_index.core.indices.query.base import BaseQueryEngine
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.llms.groq import Groq
from llama_index.vector_stores.pinecone import PineconeVectorStore

from agent.knowledge.integrations.pinecone import PineconeIntegration

from . import _config


def get_knowledge(config: _config.KnowledgeConfig) -> BaseQueryEngine:
    if config.provider == _config.KnowledgeProvider.LLAMAINDEX:
        # Ensure that settings follow LlamaIndexSettings schema
        settings = config.settings
        if not isinstance(settings, _config.LlamaIndexSettings):
            raise ValueError(
                "KnowledgeConfig settings does not satisfy LlamaIndexSettings schema!!!"
            )

        pinecone_index = PineconeIntegration.get_pinecone_index(settings.index_name)

        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=settings.namespace
        )

        cohere_api_key = os.getenv("COHERE_API_KEY")
        if not cohere_api_key:
            raise ValueError("Cohere API key not found")

        # Set global llama index settings
        Settings.embed_model = CohereEmbedding(
            api_key=cohere_api_key, model_name="embed-english-v3.0"
        )

        if settings.vector_store_modality == _config.VectorStoreModality.MULTI_MODAL:
            index = MultiModalVectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=Settings.embed_model,
                image_embed_model=Settings.embed_model,
            )
        else:
            # Default to text modality
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store, embed_model=Settings.embed_model
            )

        llm = Groq(model="llama-3.3-70b-versatile")
        response_synthesizer = get_response_synthesizer(
            response_mode=ResponseMode.SIMPLE_SUMMARIZE,
            llm=llm,
        )

        knowledge = index.as_query_engine(
            response_synthesizer=response_synthesizer,
            similarity_top_k=10,  # Increase number of retrieved documents
            similarity_cutoff=0.2,  # Lower similarity threshold (0-1 range)
            # Use menu documents with no ids for reduced context size
            filters=MetadataFilters(
                filters=[ExactMatchFilter(key="include_ids", value="False")]
            ),
        )

    else:
        raise ValueError(f"Unknown provider: {config.provider}")

    return knowledge
