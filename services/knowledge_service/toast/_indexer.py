"""
Vector store indexing operations for Toast menu knowledge base.

This module handles the indexing of processed Toast menu data into Pinecone
vector store for semantic search and retrieval by AI agents.

Key responsibilities:
- Convert Toast menu text into vector embeddings using Cohere
- Index menu items into Pinecone vector database
- Manage namespaces with timestamp-based organization
- Handle embedding generation and vector store operations
- Extract and use itemGuid as document ID and metadata

Process flow:
1. Retrieve API keys for Pinecone and Cohere services
2. Convert menu text items into Document objects with itemGuid extraction
3. Generate embeddings using Cohere embedding model
4. Index documents into Pinecone with itemGuid as doc_id and metadata
5. Return namespace identifier for future queries

Dependencies:
- Pinecone for vector storage
- Cohere for text embeddings
- LlamaIndex for document management
"""

import hashlib
import re
import time
from typing import Dict, List

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone

from services.knowledge_service._implementation import (
    get_cohere_api_key,
    get_pinecone_api_key,
)
from utils.log import logger


def _extract_item_guid(text_content: str) -> str:
    """Extract itemGuid from Toast menu item text content.

    Args:
        text_content: The formatted menu item text containing "Item GUID: {guid}"

    Returns:
        str: The extracted itemGuid, or empty string if not found
    """
    # Look for "Item GUID: " followed by the GUID
    match = re.search(r"Item GUID:\s*([a-f0-9\-]+)", text_content, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def index_to_pinecone(
    individual_items: List[Dict[str, str]],
    pinecone_index_name: str,
    pinecone_namespace: str,
    debug: bool = False,
) -> int:
    """Index individual Toast menu items to Pinecone vector store.

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
    pinecone_api_key = get_pinecone_api_key()
    cohere_api_key = get_cohere_api_key()

    if debug:
        logger.debug(
            f"[toast._indexer.index_to_pinecone] Indexing {len(individual_items)} items to Pinecone..."
        )

    # Create documents from individual items
    documents = []
    for i, item_dict in enumerate(individual_items):
        # Each item_dict has one key-value pair
        for document_name, item_text in item_dict.items():
            # Extract itemGuid from the text content
            item_guid = _extract_item_guid(item_text)

            # Create document with itemGuid as doc_id if available
            doc = Document(
                text=item_text,
                metadata={
                    "source": "toast_menu",
                    "include_ids": "True",
                    "item_index": i,
                    "file_name": document_name,
                    "itemGuid": item_guid,  # Add itemGuid to metadata
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "size_bytes": len(item_text.encode("utf-8")),
                },
                doc_id=(
                    item_guid
                    if item_guid
                    else hashlib.sha256(document_name.encode("utf-8")).hexdigest()
                ),  # Use itemGuid as document ID
            )
            documents.append(doc)

            if debug and item_guid:
                logger.debug(
                    f"[toast._indexer.index_to_pinecone] Extracted itemGuid '{item_guid}' for document: {document_name}"
                )
            elif debug and not item_guid:
                logger.warning(
                    f"[toast._indexer.index_to_pinecone] No itemGuid found for document: {document_name}"
                )

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

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Index documents
    _ = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        embed_model=embed_model,
    )

    if debug:
        logger.debug(
            f"[toast._indexer.index_to_pinecone] Successfully indexed to Pinecone namespace: {pinecone_namespace}"
        )

    return len(documents)
