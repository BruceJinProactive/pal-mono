import os

from pinecone import Pinecone


class PineconeIntegration:
    @staticmethod
    def get_pinecone_index(pinecone_index_name: str):
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise ValueError("Pinecone API key not found")

        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(pinecone_index_name)
        return index
