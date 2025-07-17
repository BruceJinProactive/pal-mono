import os
import shutil
import uuid
from datetime import datetime

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.embeddings.cohere import CohereEmbedding
from pinecone import Index, Pinecone

from db.tables.types import IntegrationProvider
from services.knowledge_service.schema import KnowledgeFile
from utils.log import logger


def _get_pinecone_api_key() -> str:
    """Retrieve and validate Pinecone API key."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY environment variable not set")
    return api_key


def _get_cohere_api_key() -> str:
    """Retrieve and validate Cohere API key."""
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise ValueError("COHERE_API_KEY environment variable not set")
    return api_key


def list_knowledge_files(
    index_name: str,
    namespace: str,
    filename: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[int, list[KnowledgeFile]]:
    try:
        index = _get_index(index_name)
        data = _list_data(index, namespace)
        file_dict = {}
        for match in data:
            if "metadata" in match and "file_name" in match["metadata"]:
                file_name = match["metadata"]["file_name"]
                if file_name not in file_dict:
                    file_dict[file_name] = KnowledgeFile(
                        name=file_name,
                        size=match["metadata"].get("file_size", 0),
                        created_at=match["metadata"].get("creation_date", "unknown"),
                    )

        file_list = sorted(file_dict.values(), key=lambda x: x.name)

        if filename:
            file_list = [f for f in file_list if filename.lower() in f.name.lower()]

        total = len(file_list)
        paginated_files = file_list[offset : offset + limit]

        return total, paginated_files
    except Exception as e:
        logger.error(f"Error retrieving knowledge files: {e}")
        raise


def upload_knowledge_file(
    index_name: str,
    namespace: str,
    file_name: str,
    content: bytes,
):
    # Initialize Cohere embeddings
    cohere_api_key = _get_cohere_api_key()
    embed_model = CohereEmbedding(
        api_key=cohere_api_key,
        model_name="embed-english-v3.0",
    )
    index = _get_index(index_name)

    tmp_dir = f"tmp_{uuid.uuid4()}"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file_name)

    try:
        with open(tmp_path, "wb") as buffer:
            buffer.write(content)

        # Load documents and split into sentences
        documents = SimpleDirectoryReader(tmp_dir).load_data()
        splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=50)
        nodes = splitter.get_nodes_from_documents(documents)

        # Prepare vectors and metadata for Pinecone
        upsert_data = []
        file_created_at = datetime.now().isoformat()
        for node in nodes:
            if isinstance(node, TextNode):
                embedding = embed_model.get_text_embedding(node.text)
            else:
                raise TypeError("Expected TextNode, got something else.")
            node.embedding = embedding
            node.metadata["file_name"] = file_name
            node.metadata["size_bytes"] = len(content)
            node.metadata["created_at"] = file_created_at
            upsert_data.append((str(uuid.uuid4()), embedding, node.metadata))

        logger.debug(
            "Uploading file to Pinecone.",
            extra={
                "index": index_name,
                "namespace": namespace,
                "file_name": file_name,
                "size": len(content),
                "num_nodes": len(nodes),
            },
        )

        # Upsert vectors into Pinecone
        index.upsert(vectors=upsert_data, namespace=namespace)

    finally:
        # Clean up the temp directory and file
        shutil.rmtree(tmp_dir, ignore_errors=True)


def delete_knowledge_file(
    index_name: str,
    namespace: str,
    file_name: str,
) -> list[str]:
    index = _get_index(index_name)
    data = _list_data(index, namespace)

    ids_to_delete = [
        match["id"] for match in data if match["metadata"].get("file_name") == file_name
    ]

    logger.debug(
        "About to delete vector data for file",
        extra={
            "index": index_name,
            "namespace": namespace,
            "file_name": file_name,
            "ids": ids_to_delete,
        },
    )
    if ids_to_delete:
        index.delete(ids=ids_to_delete, namespace=namespace)
    return ids_to_delete


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
        dict: A dictionary with deletion results

    Raises:
        Exception: If there is an error accessing the Pinecone index or deleting the vectors.
    """
    try:
        index = _get_index(index_name)

        logger.debug(
            "About to delete entire namespace",
            extra={
                "index": index_name,
                "namespace": namespace,
            },
        )

        # Delete all vectors in the namespace
        index.delete(delete_all=True, namespace=namespace)

        logger.debug(
            "Successfully deleted namespace",
            extra={
                "index": index_name,
                "namespace": namespace,
            },
        )

        return {
            "namespace": namespace,
            "index": index_name,
            "message": f"Successfully deleted all vectors in namespace '{namespace}' from index '{index_name}'.\n Please head to pinecone dashboard to delete the namespace.",
        }

    except Exception as e:
        logger.error(
            f"Error deleting namespace {namespace} from index {index_name}: {e}"
        )
        raise Exception(f"Failed to delete namespace: {str(e)}")


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
    try:
        # Get Cohere API key for embedding generation
        cohere_api_key = _get_cohere_api_key()

        # Initialize Cohere embeddings
        embed_model = CohereEmbedding(
            api_key=cohere_api_key,
            model_name="embed-english-v3.0",
        )

        # Get Pinecone index
        index = _get_index(index_name)

        logger.debug(
            "About to query vector database",
            extra={
                "index": index_name,
                "namespace": namespace,
                "query": query[:100] + "..." if len(query) > 100 else query,
                "top_k": top_k,
            },
        )

        # Generate embedding for the query
        query_embedding = embed_model.get_text_embedding(query)

        # Query the index
        response = index.query(
            vector=query_embedding,
            namespace=namespace,
            top_k=top_k,
            include_metadata=True,
        )

        matches = response["matches"]
        logger.debug(
            "Successfully queried vector database",
            extra={
                "index": index_name,
                "namespace": namespace,
                "num_results": len(matches),
            },
        )

        # Convert to basic Python types for JSON serialization
        try:
            serializable_matches = []
            for match in matches:
                serializable_match = {
                    "id": str(match.get("id", "")),
                    "score": float(match.get("score", 0.0)),
                    "metadata": dict(match.get("metadata", {})),
                }
                serializable_matches.append(serializable_match)
            return serializable_matches
        except Exception as e:
            logger.error(f"Error serializing matches: {e}")
            # Fallback: return raw matches
            return matches

    except Exception as e:
        logger.error(
            f"Error querying namespace {namespace} from index {index_name}: {e}",
            exc_info=True,
        )
        raise Exception(f"Failed to query vector database: {str(e)}")


def _get_index(index_name: str):
    pinecone_api_key = _get_pinecone_api_key()
    pc = Pinecone(pinecone_api_key)
    index = pc.Index(index_name)
    return index


def _list_data(index: Index, namespace: str):
    query = [0.0] * 1024
    response = index.query(
        vector=query,
        namespace=namespace,
        top_k=1000,  # Retrieve up to 1000 files
        include_metadata=True,
    )
    return response["matches"]


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
) -> dict:
    """Update the knowledge base for an agent based on the POS provider."""

    debug_info = {
        "pos_provider": pos_provider,
        "client_id": client_id,
        # ONLY SHOW FIRST 3 CHARACTERS OF CLIENT SECRET
        "client_secret": client_secret[:3],
        "token_api_endpoint": token_api_endpoint,
        "general_api_endpoint": general_api_endpoint,
    }

    if debug:
        logger.debug("update_agent_kb called with debug=True", extra=debug_info)

    try:
        if pos_provider == IntegrationProvider.adora:
            from services.knowledge_service.adora import AdoraMenuProcessor

            processor = AdoraMenuProcessor(debug=debug)
            result = processor.process_and_index_menu(
                store_id=store_id,
                client_id=client_id,
                client_secret=client_secret,
                pinecone_index_name=pinecone_index_name,
                pinecone_namespace=pinecone_namespace,
                token_api_endpoint=token_api_endpoint,
                general_api_endpoint=general_api_endpoint,
                include_category_in_doc_name=include_category_in_doc_name,
            )

            logger.info(
                "Successfully updated knowledge base for Adora agent",
                extra={
                    "store_id": store_id,
                    "processed_items": result.get("processed_items", 0),
                    "final_namespace": result.get("pinecone_namespace"),
                },
            )

            if debug:
                result["debug"] = debug_info

            return result

        else:
            raise ValueError(f"Unsupported POS provider: {pos_provider}")

    except Exception as e:
        logger.error(
            f"Error updating knowledge base for {pos_provider} agent",
            extra={
                "store_id": store_id,
                "error": str(e),
                "pos_provider": pos_provider,
            },
        )

        if debug:
            return {
                "debug": debug_info,
                "error": str(e),
                "pinecone_namespace": pinecone_namespace,
                "pinecone_index_name": pinecone_index_name,
                "system_prompt_menu": "",
            }

        # Re-raise the exception for production environments
        raise
