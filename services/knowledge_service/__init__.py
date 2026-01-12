from typing import Optional

from sqlalchemy.orm import Session

from db.tables.types import IntegrationProvider

from . import _implementation
from .schema import KnowledgeFile, NamespaceInfo


def list_knowledge_files(
    index_name: str,
    namespace: str,
    filename: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[int, list[KnowledgeFile]]:
    """
    Retrieve a list of knowledge files with pagination.

    Args:
        index_name: The name of the Pinecone index to query
        namespace: The namespace within the index to query
        filename: Optional filename to filter results by (case-insensitive partial match)
        limit: The maximum number of files to return
        offset: The number of files to skip

    Returns:
        tuple[int, list[dict]]: A tuple containing the total number of files and a list of file data with metadata

    Raises:
        ValueError: If the project is not found.
        RuntimeError: If there is an error retrieving the files.
    """
    return _implementation.list_knowledge_files(
        index_name, namespace, filename, limit, offset
    )


def upload_knowledge_file(
    index_name: str,
    namespace: str,
    file_name: str,
    content: bytes,
    metadata: dict | None = None,
):
    """
    Upload a text file to the project's knowledge base.
    This function gets the knowledge settings from the project's raw_config,
    generates embeddings for the text content, and stores them in Pinecone.

    Args:
        index_name (str): The index name for the pinecone vector database.
        namespace (str): The namespace within the index to upload file to.
        file_name (str): The name of the file to upload.
        content (str): The text content of the file.

    Raises:
        ValueError: If the project is not found or knowledge is not configured.
        RuntimeError: If there is an error uploading the file.
    """
    return _implementation.upload_knowledge_file(
        index_name, namespace, file_name, content, metadata
    )


def delete_knowledge_file_by_metadata(
    index_name: str,
    namespace: str,
    metadata: dict,
):
    return _implementation.delete_knowledge_file_by_metadata(
        index_name, namespace, metadata
    )


def delete_knowledge_file(
    index_name: str,
    namespace: str,
    file_name: str,
) -> list[str]:
    """
    Delete a knowledge file and its associated vector data from the Pinecone index.

    This function removes all vector embeddings associated with a specific file from the
    specified Pinecone index and namespace. It first retrieves all vectors that match
    the file name in their metadata, then deletes them from the index.

    Args:
        index_name (str): The name of the Pinecone index to delete from.
        namespace (str): The namespace within the index where the file data is stored.
        file_name (str): The name of the file whose vector data should be deleted.

    Returns:
        list[str]: A list of embedding IDs that are deleted.

    Raises:
        Exception: If there is an error accessing the Pinecone index or deleting the vectors.
    """
    return _implementation.delete_knowledge_file(index_name, namespace, file_name)


def delete_namespace(
    index_name: str,
    namespace: str,
) -> dict:
    """
    Delete all vectors from a specific namespace in the Pinecone index.

    Args:
        index_name (str): The name of the Pinecone index
        namespace (str): The namespace to delete all vectors from

    Returns:
        dict: A dictionary with deletion results including the number of deleted vectors

    Raises:
        Exception: If there is an error accessing the Pinecone index or deleting the vectors.
    """
    return _implementation.delete_namespace(index_name, namespace)


def query_vector_database(
    index_name: str,
    namespace: str,
    query: str,
    top_k: int = 10,
) -> list:
    """
    Query vectors in a specific namespace of the Pinecone index using semantic search.

    Args:
        index_name (str): The name of the Pinecone index
        namespace (str): The namespace within the index to query
        query (str): The text query to search for
        top_k (int): The number of top results to return (default: 10)

    Returns:
        list: A list of matching vectors with scores and metadata

    Raises:
        Exception: If there is an error accessing the Pinecone index or querying the vectors.
    """
    return _implementation.query_vector_database(index_name, namespace, query, top_k)


def update_agent_kb(
    pos_provider: IntegrationProvider,
    store_id: str,
    client_id: str,
    client_secret: str,
    token_api_endpoint: str,
    general_api_endpoint: str,
    pinecone_namespace: str,
    pinecone_index_name: str,
    debug: bool = False,
    include_category_in_doc_name: bool = False,
    menu_last_updated: Optional[str] = None,
    menus: Optional[list[str]] = None,
) -> dict:
    """Update the knowledge base for an agent based on the POS provider.

    Provides a unified interface for different POS systems:
    - Adora: Uses all parameters as specified
    - Square: Maps client_secret → access_token, store_id → location_id

    Args:
        pos_provider: The POS integration provider (Adora or Square)
        store_id: Store/location identifier (maps to location_id for Square)
        client_id: Client identifier for authentication
        client_secret: Client secret for authentication (maps to access_token for Square)
        token_api_endpoint: API endpoint for token operations
        general_api_endpoint: API endpoint for general operations
        pinecone_namespace: Namespace for vector storage
        pinecone_index_name: Name of the Pinecone index
        debug: Enable debug logging
        include_category_in_doc_name: Include category in document names
        menu_last_updated: Last updated date of the menu
    Returns:
        dict: Results of the knowledge base update operation

    Raises:
        ValueError: If required parameters are missing or invalid
        RuntimeError: If the update operation fails
    """
    return _implementation.update_agent_kb(
        pos_provider=pos_provider,
        store_id=store_id,
        client_id=client_id,
        client_secret=client_secret,
        token_api_endpoint=token_api_endpoint,
        general_api_endpoint=general_api_endpoint,
        pinecone_namespace=pinecone_namespace,
        pinecone_index_name=pinecone_index_name,
        debug=debug,
        include_category_in_doc_name=include_category_in_doc_name,
        menu_last_updated=menu_last_updated,
        selected_menus=menus,
    )


def list_namespaces(
    session: Session,
    account_name: Optional[str] = None,
    index_name: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> list[NamespaceInfo]:
    """
    List all knowledge base namespaces across all projects.

    Extracts namespace information from project raw_config.tools.identifiers.

    Args:
        session: Database session
        account_name: Optional filter by account name (partial match, case-insensitive)
        index_name: Optional filter by index name (partial match, case-insensitive)
        tool_name: Optional filter by tool name (partial match, case-insensitive)

    Returns:
        list[NamespaceInfo]: List of namespace information objects
    """
    return _implementation.list_namespaces(
        session=session,
        account_name=account_name,
        index_name=index_name,
        tool_name=tool_name,
    )


__all__ = [
    "list_knowledge_files",
    "upload_knowledge_file",
    "delete_knowledge_file",
    "delete_knowledge_file_by_metadata",
    "delete_namespace",
    "query_vector_database",
    "update_agent_kb",
    "list_namespaces",
    "NamespaceInfo",
]
