import os

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.indices import MultiModalVectorStoreIndex
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from phi.knowledge.agent import AgentKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.llamaindex import LlamaIndexKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

import db
from agent.knowledge.integrations.pinecone import PineconeIntegration
from agent.model import get_embedder

from . import _config


def get_knowledge(config: _config.KnowledgeConfig) -> AgentKnowledge:
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

        if settings.vector_store_modality == _config.VectorStoreModality.MULTI_MODAL:
            cohere_api_key = os.getenv("COHERE_API_KEY")
            if not cohere_api_key:
                raise ValueError("Cohere API key not found")

            # Set global llama index settings
            Settings.embed_model = CohereEmbedding(
                api_key=cohere_api_key, model_name="embed-english-v3.0"
            )

            index = MultiModalVectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=Settings.embed_model,
                image_embed_model=Settings.embed_model,
            )
        else:
            Settings.embed_model = OpenAIEmbedding(
                model="text-embedding-3-large",
                dimensions=1024,
            )

            # Default to text modality
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store, embed_model=Settings.embed_model
            )

        retriever_engine = index.as_retriever(
            similarity_top_k=3, image_similarity_top_k=3
        )

        knowledge = LlamaIndexKnowledgeBase(retriever=retriever_engine)

    elif config.provider == _config.KnowledgeProvider.DEFAULT:
        # Use phidata's combined knowledge base
        knowledge_table_name = f"{config.identifier}_knowledge"
        knowledge = CombinedKnowledgeBase(
            sources=[],
            vector_db=PgVector2(
                db_url=db.db_url,
                collection=knowledge_table_name,
                embedder=get_embedder(),
            ),
            # 2 references are added to the prompt
            num_documents=10,
        )
    else:
        raise ValueError(f"Unknown provider: {config.provider}")

    return knowledge
