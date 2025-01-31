import os

from llama_index.core import Settings, StorageContext
from llama_index.core.indices import MultiModalVectorStoreIndex
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from phi.knowledge.agent import AgentKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.llamaindex import LlamaIndexKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

import db
from agent.config import KnowledgeConfig, KnowledgeProvider
from agent.model import get_embedder
from tools.image_retrieval_tools.integrations.pinecone import PineconeIntegration


def get_knowledge(config: KnowledgeConfig) -> AgentKnowledge:
    if config.provider == KnowledgeProvider.LLAMAINDEX:
        # Use llamaindex
        pinecone_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_key:
            raise ValueError("Pinecone API key not found")

        if not config.settings:
            raise ValueError(
                "KnowledgeConfig settings required but not found in config"
            )

        if not config.settings.get("pinecone_index_name"):
            raise ValueError(
                "Pinecone index name not found in KnowledgeConfig settings"
            )

        pinecone_integration = PineconeIntegration(
            pinecone_api_key=pinecone_key,
            pinecone_index_name=config.settings["pinecone_index_name"],
            pinecone_namespace="default",
            pinecone_dim=1408,
            vertexai_project_id="windsor-demo",
        )

        cohere_api_key = os.getenv("COHERE_API_KEY")
        if not cohere_api_key:
            raise ValueError("Cohere API key not found")

        # Set global llama index settings
        Settings.embed_model = CohereEmbedding(
            api_key=cohere_api_key, model_name="embed-english-v3.0"
        )
        vector_store = PineconeVectorStore(pinecone_index=pinecone_integration.index)

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store, image_store=vector_store
        )

        index = MultiModalVectorStoreIndex.from_documents(
            [], storage_context=storage_context, image_embed_model=Settings.embed_model
        )
        retriever_engine = index.as_retriever(
            similarity_top_k=3, image_similarity_top_k=3
        )
        knowledge = LlamaIndexKnowledgeBase(retriever=retriever_engine)

    elif config.provider == KnowledgeProvider.DEFAULT:
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
