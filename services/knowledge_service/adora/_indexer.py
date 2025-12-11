"""
Vector store indexing operations for Adora menu knowledge base.

This module handles the indexing of processed menu data into Pinecone
vector store for semantic search and retrieval by AI agents.

Key responsibilities:
- Convert menu text into vector embeddings using Cohere
- Index menu items into Pinecone vector database
- Manage namespaces with timestamp-based organization
- Handle embedding generation and vector store operations

Process flow:
1. Retrieve API keys for Pinecone and Cohere services
2. Convert menu text items into Document objects
3. Generate embeddings using Cohere embedding model
4. Index documents into Pinecone with metadata
5. Return namespace identifier for future queries

Dependencies:
- Pinecone for vector storage
- Cohere for text embeddings
- LlamaIndex for document management
"""

import time
from typing import Dict, List

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SimpleNodeParser
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
    debug: bool = False,
) -> int:
    """Index individual menu items to Pinecone vector store.

    Args:
        individual_items: Menu items as key-value dictionaries with formatted text
        pinecone_index_name: Pinecone index name
        pinecone_namespace: Pinecone namespace for indexing
        debug: Enable debug logging

    Returns:
        int: Number of documents indexed

    Raises:
        Exception: If indexing fails
    """
    # Get API keys from centralized functions
    pinecone_api_key = _get_pinecone_api_key()
    cohere_api_key = _get_cohere_api_key()

    logger.debug(
        "[indexer.index_to_pinecone] Indexing %s items to Pinecone...",
        len(individual_items),
    )

    # Create documents from individual items
    documents = []
    for i, item_dict in enumerate(individual_items):
        # Each item_dict has one key-value pair
        for document_name, item_text in item_dict.items():
            doc = Document(
                text=item_text,
                metadata={
                    "include_ids": "True",
                    "item_index": i,
                    "file_name": document_name,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "size_bytes": len(item_text.encode("utf-8")),
                },
            )
            documents.append(doc)

    # Initialize Pinecone
    pc = Pinecone(api_key=pinecone_api_key)
    pinecone_index = pc.Index(pinecone_index_name)

    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index, namespace=pinecone_namespace
    )

    embed_model = CohereEmbedding(
        api_key=cohere_api_key,
        model_name="embed-english-v3.0",
    )

    node_parser = SimpleNodeParser.from_defaults(
        chunk_size=1000000,  # effectively disables chunking for menu items
        chunk_overlap=0,
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Index
    _ = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        embed_model=embed_model,
        transformations=[node_parser],
    )

    logger.info(
        "Successfully indexed to Pinecone",
        extra={
            "namespace": pinecone_namespace,
            "document_count": len(documents),
        },
    )

    return len(documents)
