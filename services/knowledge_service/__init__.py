from db.tables.types import IntegrationProvider

from . import _implementation
from .schema import KnowledgeFile


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
        index_name, namespace, file_name, content
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
) -> dict:
    """
    Update the knowledge base for an agent.

    Args:
        pos_provider (IntegrationProvider): The POS provider to use to update the knowledge base. Example: ADORA, TOAST, SQUARE, OLO.
        store_id (str): The ID of the store to update the knowledge base for.
        client_id (str): The ID of the client to update the knowledge base for.
        client_secret (str): The secret of the client to update the knowledge base for.
        token_api_endpoint (str): The complete URL for the token endpoint (e.g., "https://identity.adorapos.net/connect/token"). Required.
        general_api_endpoint (str): The complete URL for the menu endpoint (e.g., "https://public.api.adorapos.net/api/v1/OrderHub/menu"). Required.
        pinecone_namespace (str): The namespace to upsert the knowledge base to.
        pinecone_index_name (str): The name of the Pinecone index to use.
        debug (bool): Whether to enable debug mode.

    Returns:
        dict: A dictionary of the following:
            - system prompt menu: Menu information added to project config
            - pinecone namespace name: The namespace name in Pinecone the menu is upserted to

    When debug is enabled, the endpoint will return the following:
    - debug:
        - pos_provider: POS provider name
        - store_id: Store ID
        - client_id: Client ID
        - client_secret: Client secret
        - token_api_endpoint: Token API endpoint URL
        - general_api_endpoint: General API endpoint URL
    """
    return _implementation.update_agent_kb(
        pos_provider,
        store_id,
        client_id,
        client_secret,
        token_api_endpoint,
        general_api_endpoint,
        pinecone_namespace,
        pinecone_index_name,
        debug,
    )


__all__ = [
    "list_knowledge_files",
    "upload_knowledge_file",
    "delete_knowledge_file",
    "delete_namespace",
    "update_agent_kb",
]
