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
from datetime import datetime
from typing import Any, Dict, Optional

from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone

from services.knowledge_service._implementation import (
    _get_cohere_api_key,
    _get_pinecone_api_key,
)
from utils.log import logger


def index_to_pinecone(
    documents: Dict[str, str],
    menu_data: Dict[str, Any],
    pinecone_index_name: str,
    pinecone_namespace: str,
    location_id: str,
    location_name: Optional[str] = None,
    restaurant_name: str = "ume",
) -> Dict[str, Any]:
    """Index Square menu documents to Pinecone vector store.

    Args:
        documents: Dictionary mapping document names to text content
        menu_data: Original menu data for metadata
        pinecone_index_name: Name of the Pinecone index to use
        pinecone_namespace: Base namespace for the index
        location_id: Square location ID for metadata
        location_name: Optional location name for metadata
        restaurant_name: Restaurant name for namespace creation

    Returns:
        dict: Indexing results including success status and statistics

    Raises:
        RuntimeError: If indexing fails
    """
    try:
        logger.debug(f"Starting Pinecone indexing for Square location {location_id}")

        if not documents:
            logger.warning("No documents provided for indexing")
            return {
                "success": False,
                "error": "No documents to index",
                "documents_processed": 0,
                "vectors_created": 0,
            }

        # Get API keys
        pinecone_api_key = _get_pinecone_api_key()
        cohere_api_key = _get_cohere_api_key()

        # Create timestamped namespace following the notebook pattern
        current_date = datetime.now().strftime("%Y-%m-%d")
        final_namespace = f"{restaurant_name}_{location_name or location_id}_{location_id}_{current_date}"

        logger.debug(f"Using namespace: {final_namespace}")

        # Initialize Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        pinecone_index = pc.Index(pinecone_index_name)

        # Setup embedding model
        embed_model = CohereEmbedding(
            api_key=cohere_api_key,
            model_name="embed-english-v3.0",
        )
        Settings.embed_model = embed_model

        # Create vector store
        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=final_namespace
        )

        # Convert documents to LlamaIndex Document objects
        llama_documents = []

        for doc_name, content in documents.items():
            doc = Document(
                text=content,
                metadata={
                    "source": "square_menu",
                    "location": location_name or location_id,
                    "location_id": location_id,
                    "document_type": "menu",
                    "document_name": doc_name,
                    "item_count": menu_data.get("item_count", 0),
                    "total_objects": menu_data.get("total_objects", 0),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "size_bytes": len(content.encode("utf-8")),
                    "file_name": f"{restaurant_name}_{location_name or location_id}_{doc_name.lower().replace(' ', '_')}_{current_date}.json",
                },
            )
            llama_documents.append(doc)

        logger.debug(f"Created {len(llama_documents)} LlamaIndex documents")

        # Parse documents into nodes (optional chunking)
        node_parser = SentenceSplitter(chunk_size=2048 * 4, chunk_overlap=0)
        nodes = node_parser.get_nodes_from_documents(
            llama_documents, show_progress=False
        )

        # Create storage context and index
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=embed_model,
        )

        logger.debug(f"Successfully indexed Square menu for location {location_id}")

        return {
            "success": True,
            "documents_processed": len(documents),
            "vectors_created": len(nodes),
            "pinecone_index": pinecone_index_name,
            "pinecone_namespace": final_namespace,
            "location_id": location_id,
            "location_name": location_name,
            "restaurant_name": restaurant_name,
            "nodes_created": len(nodes),
            "index_object": index,  # Return index for potential queries
        }

    except Exception as e:
        logger.error(f"Error indexing Square menu to Pinecone: {e}")
        raise RuntimeError(f"Failed to index Square menu: {e}")


def index_individual_items_to_pinecone(
    menu_data: Dict[str, Any],
    pinecone_index_name: str,
    pinecone_namespace: str,
    location_id: str,
    location_name: Optional[str] = None,
    restaurant_name: str = "ume",
) -> Dict[str, Any]:
    """Index individual Square menu items to Pinecone following the notebook pattern.

    Args:
        menu_data: Processed menu data with individual items
        pinecone_index_name: Name of the Pinecone index to use
        pinecone_namespace: Base namespace for the index
        location_id: Square location ID
        location_name: Optional location name
        restaurant_name: Restaurant name for namespace creation

    Returns:
        dict: Indexing results including success status and statistics

    Raises:
        RuntimeError: If indexing fails
    """
    try:
        logger.debug(
            f"Starting individual item indexing for Square location {location_id}"
        )

        menu_items = menu_data.get("menu_items", [])
        if not menu_items:
            logger.warning("No menu items provided for indexing")
            return {
                "success": False,
                "error": "No menu items to index",
                "items_processed": 0,
                "vectors_created": 0,
            }

        # Get API keys
        pinecone_api_key = _get_pinecone_api_key()
        cohere_api_key = _get_cohere_api_key()

        # Create timestamped namespace
        current_date = datetime.now().strftime("%Y-%m-%d")
        final_namespace = f"{restaurant_name}_{location_name or location_id}_{location_id}_{current_date}"

        logger.debug(f"Using namespace: {final_namespace}")

        # Initialize Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        pinecone_index = pc.Index(pinecone_index_name)

        # Setup embedding model
        embed_model = CohereEmbedding(
            api_key=cohere_api_key,
            model_name="embed-english-v3.0",
        )
        Settings.embed_model = embed_model

        # Create vector store
        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=final_namespace
        )

        # Convert menu items to LlamaIndex Document objects
        documents = []

        for item in menu_items:
            # Create structured text following exact notebook pattern
            item_name = item.get("name", "Unknown Item")
            item_text = f"Item: {item_name}\n"
            item_text += f"Item ID: {item.get('id', 'N/A')}\n"
            item_text += f"Variation ID: {item.get('_variation_id', 'N/A')}\n"

            # Add modifiers information - follow exact notebook pattern
            modifiers = item.get("modifiers", [])
            if modifiers:
                item_text += "Available Modifiers:\n"
                for mod_group in modifiers:
                    list_name = mod_group.get("list_name", "Options")
                    item_text += f"  {list_name}:\n"
                    for modifier in mod_group.get("modifiers", []):
                        mod_name = modifier.get("name", "Unknown")
                        mod_id = modifier.get("id", "N/A")
                        item_text += f"    - {mod_name} (ID: {mod_id})\n"
            else:
                item_text += "No modifiers available\n"

            # Create document with metadata following notebook pattern
            doc = Document(
                text=item_text,
                metadata={
                    "source": "modifier_menu",
                    "location": location_name or location_id,
                    "location_id": location_id,
                    "type": "menu_item",
                    "item_name": item_name,
                    "item_id": item.get("id"),
                    "variation_id": item.get("_variation_id"),
                    "file_name": f"{restaurant_name}_{location_name or location_id}_{item_name.replace(' ', '_').lower()}_{current_date}.json",
                },
            )
            documents.append(doc)

        logger.debug(f"Created {len(documents)} individual item documents")

        # Parse documents into nodes
        node_parser = SentenceSplitter(chunk_size=2048 * 4, chunk_overlap=0)
        nodes = node_parser.get_nodes_from_documents(documents, show_progress=False)

        # Create storage context and index
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=embed_model,
        )

        logger.debug(f"Successfully indexed {len(menu_items)} individual items")

        return {
            "success": True,
            "items_processed": len(menu_items),
            "vectors_created": len(nodes),
            "pinecone_index": pinecone_index_name,
            "pinecone_namespace": final_namespace,
            "location_id": location_id,
            "location_name": location_name,
            "restaurant_name": restaurant_name,
            "nodes_created": len(nodes),
            "index_object": index,
        }

    except Exception as e:
        logger.error(f"Error indexing individual items to Pinecone: {e}")
        raise RuntimeError(f"Failed to index individual items: {e}")


def delete_location_vectors(
    pinecone_index_name: str,
    location_id: str,
    location_name: Optional[str] = None,
    restaurant_name: str = "ume",
) -> Dict[str, Any]:
    """Delete all vectors for a specific Square location.

    Args:
        pinecone_index_name: Name of the Pinecone index
        location_id: Square location ID to delete
        location_name: Optional location name
        restaurant_name: Restaurant name for namespace pattern

    Returns:
        dict: Deletion results including success status

    Raises:
        RuntimeError: If deletion fails
    """
    try:
        logger.debug(f"Deleting vectors for Square location {location_id}")

        # Get API key
        pinecone_api_key = _get_pinecone_api_key()

        # Initialize Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        pinecone_index = pc.Index(pinecone_index_name)

        # Create namespace pattern - delete all namespaces for this location
        current_date = datetime.now().strftime("%Y-%m-%d")
        namespace_pattern = f"{restaurant_name}_{location_name or location_id}_{location_id}_{current_date}"

        # Delete the namespace (this deletes all vectors in that namespace)
        try:
            pinecone_index.delete(delete_all=True, namespace=namespace_pattern)
            vectors_deleted = (
                "all"  # Pinecone doesn't return exact count for namespace deletion
            )
        except Exception as e:
            logger.warning(f"Error deleting namespace {namespace_pattern}: {e}")
            vectors_deleted = 0

        logger.debug(f"Successfully deleted vectors for Square location {location_id}")
        return {
            "success": True,
            "location_id": location_id,
            "location_name": location_name,
            "namespace_deleted": namespace_pattern,
            "vectors_deleted": vectors_deleted,
        }

    except Exception as e:
        logger.error(f"Error deleting Square vectors: {e}")
        raise RuntimeError(f"Failed to delete Square vectors: {e}")


def get_indexing_stats(
    pinecone_index_name: str,
    location_id: Optional[str] = None,
    location_name: Optional[str] = None,
    restaurant_name: str = "ume",
) -> Dict[str, Any]:
    """Get statistics about indexed Square menu data.

    Args:
        pinecone_index_name: Name of the Pinecone index
        location_id: Optional location ID to filter results
        location_name: Optional location name
        restaurant_name: Restaurant name for namespace pattern

    Returns:
        dict: Statistics about indexed vectors

    Raises:
        RuntimeError: If stats retrieval fails
    """
    try:
        logger.debug("Getting indexing stats for Square menu data")

        # Get API key
        pinecone_api_key = _get_pinecone_api_key()

        # Initialize Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        pinecone_index = pc.Index(pinecone_index_name)

        # Get index stats
        index_stats = pinecone_index.describe_index_stats()

        # If location is specified, try to get namespace-specific stats
        namespace_stats = None
        if location_id:
            current_date = datetime.now().strftime("%Y-%m-%d")
            namespace = f"{restaurant_name}_{location_name or location_id}_{location_id}_{current_date}"

            if (
                hasattr(index_stats, "namespaces")
                and namespace in index_stats.namespaces
            ):
                namespace_stats = index_stats.namespaces[namespace]

        return {
            "success": True,
            "index_name": pinecone_index_name,
            "location_filter": location_id,
            "location_name": location_name,
            "restaurant_name": restaurant_name,
            "index_stats": index_stats,
            "namespace_stats": namespace_stats,
        }

    except Exception as e:
        logger.error(f"Error getting Square indexing stats: {e}")
        raise RuntimeError(f"Failed to get indexing stats: {e}")
