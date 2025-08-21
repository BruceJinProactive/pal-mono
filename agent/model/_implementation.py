import os
from typing import Any, AsyncIterator, Mapping

from agno.models.azure.openai_chat import AzureOpenAI
from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from utils.log import logger

from ._config import ModelOptions


def _get_deployment_name(model_option: ModelOptions) -> str:
    """Get the Azure deployment name from environment variable."""
    deployment_name = os.getenv(model_option.env_key)
    if not deployment_name:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")
    return deployment_name


def _build_azure_client() -> AsyncAzureOpenAI:
    """Build Azure OpenAI client with required configuration."""
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY environment variable not found.")

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not azure_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT environment variable not found.")

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    return AsyncAzureOpenAI(
        api_key=api_key,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
    )


async def call_llm_default(
    model_option: ModelOptions, params: Mapping[str, Any]
) -> ChatCompletion:
    """
    Makes a non-streaming LLM request using Azure OpenAI.

    Args:
        model_option: Model to use for this request
        params: dict of OpenAI API compatible parameters; model and stream keys will be dropped.

    Returns:
        OpenAI API compatible completions response
    """
    client = _build_azure_client()

    # Resolve Azure deployment name and inject as 'model'
    deployment_name = _get_deployment_name(model_option)

    sanitized_params = {key: value for key, value in params.items() if key != "stream"}
    sanitized_params["model"] = deployment_name
    try:
        response = await client.chat.completions.create(
            stream=False, **sanitized_params
        )
        if not isinstance(response, ChatCompletion):
            raise TypeError("Unexpected return type from Azure OpenAI.")
        return response
    except Exception:
        logger.exception("Chat completion call to Azure OpenAI failed.")
        raise


async def call_llm_stream(
    model_option: ModelOptions, params: Mapping[str, Any]
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Makes a streaming LLM request using Azure OpenAI.

    Args:
        model_option: Model to use for this request
        params: dict of OpenAI API compatible parameters; model and stream keys will be dropped.

    Returns:
        OpenAI API compatible completions response
    """
    client = _build_azure_client()

    # Resolve Azure deployment name and inject as 'model'
    deployment_name = _get_deployment_name(model_option)
    sanitized_params = {key: value for key, value in params.items() if key != "stream"}
    sanitized_params["model"] = deployment_name
    try:
        response = await client.chat.completions.create(stream=True, **sanitized_params)
        if not hasattr(response, "__aiter__"):
            raise TypeError("Unexpected return type from Azure OpenAI.")
        return response
    except Exception:
        logger.exception("Chat completion call to Azure OpenAI failed.")
        raise


def build_agno_model(model_option: ModelOptions) -> AzureOpenAI:
    """
    Returns an Agno agent model that calls Azure OpenAI to make LLM requests.
    """
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AZURE_OPENAI_API_KEY environment variable not found.")

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not azure_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT environment variable not found.")

    deployment_name = _get_deployment_name(model_option)
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

    return AzureOpenAI(
        id=deployment_name,
        api_key=api_key,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
    )
