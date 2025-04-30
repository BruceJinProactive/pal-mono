import os
import shutil
import uuid

import openai
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from pinecone import Index, Pinecone

from utils.log import logger

# Check if Pinecone API key exists
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not PINECONE_API_KEY:
    raise ValueError("Pinecone API key not found")


def list_knowledge_files(
    index_name: str,
    namespace: str,
) -> list[str]:
    try:
        index = _get_index(index_name)
        data = _list_data(index, namespace)

        # Use a set to avoid duplicates
        file_set = set()
        for match in data:
            if "metadata" in match and "file_name" in match["metadata"]:
                file = match["metadata"]["file_name"]
                file_set.add(file)

        return sorted(list(file_set))
    except Exception as e:
        logger.error(f"Error retrieving knowledge files: {e}")
        raise


def upload_knowledge_file(
    index_name: str,
    namespace: str,
    file_name: str,
    content: bytes,
):
    # OpenAI client for embeddings
    client = openai.OpenAI()
    index = _get_index(index_name)

    def get_openai_embeddings(text):
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=1024,
        )
        return response.data[0].embedding

    tmp_dir = f"tmp_{uuid.uuid4()}"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file_name)

    try:
        with open(tmp_path, "wb") as buffer:
            buffer.write(content)

        # Load documents and split into sentences
        documents = SimpleDirectoryReader(tmp_dir).load_data()
        splitter = SentenceSplitter(chunk_size=2048, chunk_overlap=50)
        nodes = splitter.get_nodes_from_documents(documents)

        # Prepare vectors and metadata for Pinecone
        upsert_data = []
        for node in nodes:
            if isinstance(node, TextNode):
                embedding = get_openai_embeddings(node.text)
            else:
                raise TypeError("Expected TextNode, got something else.")
            node.embedding = embedding
            node.metadata["file_name"] = file_name
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


def _get_index(index_name: str):
    pc = Pinecone(PINECONE_API_KEY)
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
