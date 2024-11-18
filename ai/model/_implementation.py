from enum import Enum
from os import getenv

from openai import AsyncOpenAI, OpenAI
from phi.embedder.openai import OpenAIEmbedder
from phi.model.openai.chat import OpenAIChat
from phi.model.openai.like import OpenAILike
from pydantic import BaseModel, Field

# Get the MODEL_ROUTER_BASE_URL environment variable, or use a default value if not set
MODEL_ROUTER_BASE_URL = getenv(
    "MODEL_ROUTER_BASE_URL",
    "https://25qnn07d2j.execute-api.us-west-1.amazonaws.com/lat/",  # lat,
)
MODEL_ROUTER_API_KEY = getenv("MODEL_ROUTER_API_KEY", "")


class OutputModel(BaseModel):
    content: str = Field(..., description="plain response content")
    escalated: bool = Field(..., description="system info escalated field")


class ModelName(str, Enum):
    MEDIUM = "medium"
    SMALL = "small"


class EmbedderName(str, Enum):
    SMALL = "text-embedding-3-small"


def get_client() -> OpenAI:
    client = OpenAI(
        api_key="dummy",  # This argument is required by OpenAI(), but not used by model router
        default_headers={
            "x-api-key": MODEL_ROUTER_API_KEY,
        },
        base_url=MODEL_ROUTER_BASE_URL,
    )
    return client


def get_async_client() -> AsyncOpenAI:
    client = AsyncOpenAI(
        api_key="dummy",  # This argument is required by AsyncOpenAI(), but not used by model router
        default_headers={
            "x-api-key": MODEL_ROUTER_API_KEY,
        },
        base_url=MODEL_ROUTER_BASE_URL,
    )
    return client


def get_model(model_name: str = ModelName.MEDIUM, stream: bool = False) -> OpenAIChat:
    if stream:
        model = OpenAIChat(id="gpt-4o")
        return model
    else:
        model = OpenAILike(
            id=model_name, client=get_client(), async_client=get_async_client()
        )
        return model


def get_embedder():
    return OpenAIEmbedder(model=EmbedderName.SMALL)
