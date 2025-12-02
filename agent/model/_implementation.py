import os
from typing import Any, AsyncIterator, Mapping

from agno.models.openai import OpenAIChat
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from utils.dd import traced
from utils.log import logger

from ._config import ModelOptions


def _build_truefoundry_client() -> AsyncOpenAI:
    """Build OpenAI client configured for TrueFoundry."""
    api_key = os.getenv("TRUEFOUNDRY_API_KEY")
    if not api_key:
        raise ValueError("TRUEFOUNDRY_API_KEY environment variable not found.")

    base_url = os.getenv("TRUEFOUNDRY_BASE_URL")
    if not base_url:
        raise ValueError("TRUEFOUNDRY_BASE_URL environment variable not found.")

    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )


@task(name="LLM Call Default")
async def call_llm_default(
    model_option: ModelOptions, params: Mapping[str, Any]
) -> ChatCompletion:
    """
    Makes a non-streaming LLM request using TrueFoundry gateway.

    Args:
        model_option: Model to use for this request
        params: dict of OpenAI API compatible parameters; model and stream keys will be dropped.

    Returns:
        OpenAI API compatible completions response
    """
    client = _build_truefoundry_client()

    model_id = os.getenv(model_option.env_key)
    if not model_id:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")

    sanitized_params = {key: value for key, value in params.items() if key != "stream"}
    sanitized_params["model"] = model_id

    LLMObs.annotate(
        input_data=sanitized_params,
        tags={
            "model": model_id,
            "streaming": False,
            "provider": "truefoundry",
        },
    )
    try:
        response = await client.chat.completions.create(
            stream=False, **sanitized_params
        )
        if not isinstance(response, ChatCompletion):
            raise TypeError("Unexpected return type from OpenAI client.")
        return response
    except Exception:
        logger.exception("Chat completion call to TrueFoundry failed.")
        raise


@task(name="LLM Call Stream")
async def call_llm_stream(
    model_option: ModelOptions, params: Mapping[str, Any]
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Makes a streaming LLM request using TrueFoundry gateway.

    Args:
        model_option: Model to use for this request
        params: dict of OpenAI API compatible parameters; model and stream keys will be dropped.

    Returns:
        OpenAI API compatible completions response
    """
    client = _build_truefoundry_client()

    model_id = os.getenv(model_option.env_key)
    if not model_id:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")

    sanitized_params = {key: value for key, value in params.items() if key != "stream"}
    sanitized_params["model"] = model_id

    LLMObs.annotate(
        tags={
            "model": model_id,
            "streaming": True,
            "provider": "truefoundry",
        }
    )
    try:
        response = await client.chat.completions.create(stream=True, **sanitized_params)
        if not hasattr(response, "__aiter__"):
            raise TypeError("Unexpected return type from OpenAI client.")
        return response
    except Exception:
        logger.exception("Chat completion call to TrueFoundry failed.")
        raise


@traced("Build Agno Model")
def build_agno_model(model_option: ModelOptions) -> OpenAIChat:
    """
    Returns an Agno agent model that calls TrueFoundry gateway to make LLM requests.
    """
    api_key = os.getenv("TRUEFOUNDRY_API_KEY")
    if not api_key:
        raise ValueError("TRUEFOUNDRY_API_KEY environment variable not found.")

    base_url = os.getenv("TRUEFOUNDRY_BASE_URL")
    if not base_url:
        raise ValueError("TRUEFOUNDRY_BASE_URL environment variable not found.")

    # Get model ID from environment variable
    model_id = os.getenv(model_option.env_key)
    if not model_id:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")

    return OpenAIChat(
        id=model_id,
        api_key=api_key,
        base_url=base_url,
    )
