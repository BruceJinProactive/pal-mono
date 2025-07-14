from enum import Enum
from os import getenv

from agno.embedder.openai import OpenAIEmbedder
from agno.models.google.gemini import Gemini
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, Field

# Get the MODEL_ROUTER_BASE_URL environment variable, or use a default value if not set
MODEL_ROUTER_BASE_URL = getenv(
    "MODEL_ROUTER_BASE_URL",
    "https://25qnn07d2j.execute-api.us-west-1.amazonaws.com/lat/",  # lat,
)
MODEL_ROUTER_API_KEY = getenv("MODEL_ROUTER_API_KEY", "")


class BaseOutputModel(BaseModel):
    content: str = Field(..., description="plain response content")
    escalated: bool = Field(..., description="system info escalated field")


class ModelName(str, Enum):
    MEDIUM = "medium"
    SMALL = "small"


class EmbedderName(str, Enum):
    SMALL = "text-embedding-3-small"


def get_client() -> OpenAI:
    """
    Get the model client instance providied by model router.

    Returns:
        A instance of model router client with same usage as openai client
    """
    client = OpenAI(
        api_key="dummy",  # This argument is required by OpenAI(), but not used by model router
        default_headers={
            "x-api-key": MODEL_ROUTER_API_KEY,
        },
        base_url=MODEL_ROUTER_BASE_URL,
    )
    return client


def get_async_client() -> AsyncOpenAI:
    """
    Get the model async client instance providied by model router.

    Returns:
        A instance of model router async client with same usage as async openai client
    """
    client = AsyncOpenAI(
        api_key="dummy",  # This argument is required by AsyncOpenAI(), but not used by model router
        default_headers={
            "x-api-key": MODEL_ROUTER_API_KEY,
        },
        base_url=MODEL_ROUTER_BASE_URL,
    )
    return client


def get_gemini_model():
    api_key = getenv("GEMINI_API_KEY", "")
    assert api_key, "GEMINI_API_KEY is not set"
    return Gemini(id="gemini-2.0-flash", api_key=api_key)


def get_embedder():
    """
    Get the OpenAIEmbedder instance configured with the appropriate embedding model.

    Returns:
        OpenAIEmbedder: An instance of OpenAIEmbedder configured with the embedding model from settings.
    """
    return OpenAIEmbedder(id=EmbedderName.SMALL)
