"""
Square menu indexing for Pinecone vector storage.

This module handles the indexing of processed Square menu data into
Pinecone vector stores for semantic search and retrieval.

Key responsibilities:
- Convert Square menu data into vector embeddings using Cohere
- Index menu items into Pinecone vector database with structured metadata
- Manage namespaces with timestamp-based organization
- Handle embedding generation and vector store operations

Process flow:
1. Retrieve API keys for Pinecone and Cohere services
2. Convert menu items into Document objects with metadata
3. Generate embeddings using Cohere embedding model
4. Index documents into Pinecone with location-specific namespaces
5. Return indexing results and namespace information

Dependencies:
- Pinecone for vector storage
- Cohere for text embeddings
- LlamaIndex for document management
"""

import time
from typing import Dict, List

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone

from services.knowledge_service._implementation import (
    _get_cohere_api_key,
    _get_pinecone_api_key,
)
from utils.log import logger


def index_to_pinecone(
    individual_items: List[Dict[str, str]],
    pinecone_index_name: str,
    pinecone_namespace: str,
) -> int:
    """Index per-item documents to Pinecone (aligned with Adora/Toast)."""
    pinecone_api_key = _get_pinecone_api_key()
    cohere_api_key = _get_cohere_api_key()

    logger.debug(
        "[square._indexer.index_to_pinecone] Indexing %s items...",
        len(individual_items),
    )

    # Guard: no items to index
    if not individual_items:
        logger.debug("[square._indexer.index_to_pinecone] No items to index; skipping.")
        return 0

    # Prepare documents
    documents: List[Document] = []
    for i, item_dict in enumerate(individual_items):
        for file_name, text in item_dict.items():
            documents.append(
                Document(
                    text=text,
                    id_=file_name,
                    metadata={
                        "include_ids": "True",
                        "item_index": i,
                        "file_name": file_name,
                        "created_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        ),
                        "size_bytes": len(text.encode("utf-8")),
                    },
                )
            )

    # Pinecone + embeddings
    pc = Pinecone(api_key=pinecone_api_key)
    pinecone_index = pc.Index(pinecone_index_name)
    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index, namespace=pinecone_namespace
    )
    embed_model = CohereEmbedding(
        api_key=cohere_api_key,
        model_name="embed-english-v3.0",
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Index
    _ = VectorStoreIndex.from_documents(
        documents, storage_context=storage_context, embed_model=embed_model
    )

    logger.debug(
        "[square._indexer.index_to_pinecone] Indexed %s docs to %s/%s",
        len(documents),
        pinecone_index_name,
        pinecone_namespace,
    )
    return len(documents)


# The old Square-specific deletion/stats helpers were unused and removed.
