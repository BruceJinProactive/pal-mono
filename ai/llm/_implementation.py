from os import getenv

from openai import OpenAI
from phi.embedder.openai import OpenAIEmbedder
from phi.llm.openai.like import OpenAILike
from pydantic import BaseModel, Field

from . import _settings

# Get the MODEL_ROUTER_BASE_URL environment variable, or use a default value if not set
MODEL_ROUTER_BASE_URL = getenv(
    "MODEL_ROUTER_BASE_URL",
    "https://25qnn07d2j.execute-api.us-west-1.amazonaws.com/lat/",  # lat,
)
MODEL_ROUTER_API_KEY = getenv("MODEL_ROUTER_API_KEY")


class OutputModel(BaseModel):
    content: str = Field(..., description="plain response content")
    escalated: bool = Field(..., description="system info escalated field")


def get_client():
    client = OpenAI(
        api_key="dummy",  # This argument is required by OpenAI(), but not used by model router
        default_headers={"x-api-key": MODEL_ROUTER_API_KEY},
        base_url=MODEL_ROUTER_BASE_URL,
    )
    return client


def get_model(model_name: str = _settings.ai_settings.standard):
    model = OpenAILike(model=model_name, client=get_client())
    return model


def get_embedder():
    return OpenAIEmbedder(model=_settings.ai_settings.embedding_model)
