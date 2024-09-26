from enum import Enum
from os import getenv

from phi.embedder.openai import OpenAIEmbedder
from phi.llm.openai import OpenAIChat
from phi.llm.openai.like import OpenAILike
from pydantic import BaseModel, Field

from . import _settings

# Get the MODEL_ROUTER_BASE_URL environment variable, or use a default value if not set
MODEL_ROUTER_BASE_URL = getenv(
    "MODEL_ROUTER_BASE_URL",
    "https://4msggkaz6wph3hx7hxppwcqn7e0xjlmb.lambda-url.us-west-1.on.aws/",  # lat,
)


class LLM(Enum):
    OPENAI = "OPENAI"
    LEPTON = "LEPTON"
    MODAL = "MODAL"
    ROUTER = "ROUTER"


class OutputModel(BaseModel):
    content: str = Field(..., description="plain response content")
    escalated: bool = Field(..., description="system info escalated field")


def get_llm(llm_name: LLM):
    if llm_name == LLM.OPENAI:
        return OpenAIChat(
            model=_settings.ai_settings.gpt_4o_2024_08_06,
            max_tokens=4096,
            temperature=0.9,
        )
    elif llm_name == LLM.LEPTON:
        return OpenAILike(
            model="gpt-3.5-turbo",
            api_key=getenv("LEPTON_API_KEY"),
            base_url="https://kfxrnfa5-pail-test.tin.lepton.run/api/v1/",
            max_tokens=16384,
            temperature=0.9,
            top_p=0.9,
        )
    elif llm_name == LLM.MODAL:
        return OpenAILike(
            model="OpenHermes-2.5-Mistral-7B-dpo",
            api_key=getenv("MODAL_API_KEY"),
            base_url="https://proactive-ai-lab--openai-b-fastapi-app.modal.run/",
            max_tokens=16384,
            temperature=0.9,
            top_p=0.9,
        )
    elif llm_name == LLM.ROUTER:
        return OpenAILike(base_url=MODEL_ROUTER_BASE_URL)
    else:
        raise ValueError(f"Invalid model name: {llm_name}")


def get_embedder():
    return OpenAIEmbedder(model=_settings.ai_settings.embedding_model)
