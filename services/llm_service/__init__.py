from typing import AsyncIterator

from agno.models.openai.like import OpenAILike
from portkey_ai.api_resources.types.chat_complete_type import (
    ChatCompletionChunk,
    ChatCompletions,
)

from . import _implementation as implementation
from .schema import ModelOptions


async def call_llm_default(model_option: ModelOptions, params: dict) -> ChatCompletions:
    """
    Makes a non-streaming LLM request using Portkey.

    Args:
    model_options: Model to use for this request
    params: dict of OpenAI API compatible parameters, excluding model and stream

    Returns:
    OpenAI API compatible completions response
    """
    return await implementation.call_llm_default(model_option, params)


async def call_llm_stream(
    model_option: ModelOptions, params: dict
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Makes a streaming LLM request using Portkey.

    Args:
    model_options: Model to use for this request
    params: dict of OpenAI API compatible parameters, excluding model and stream

    Returns:
    OpenAI API compatible completions response
    """
    return await implementation.call_llm_stream(model_option, params)


def build_agno_model(model_option: ModelOptions) -> OpenAILike:
    """
    Returns an Agno agent model that calls Portkey to make LLM requests.
    """
    return implementation.build_agno_model(model_option)


__all__ = ["call_llm_default", "call_llm_stream", "build_agno_model"]
