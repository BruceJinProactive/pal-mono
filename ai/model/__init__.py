from openai import AsyncOpenAI, OpenAI
from phi.model.openai.like import OpenAILike

from . import _implementation

OutputModel = _implementation.OutputModel
ModelName = _implementation.ModelName


def get_model(
    model_name: str = ModelName.MEDIUM,
) -> OpenAILike:
    """
    Get the appropriate LLM (Large Language Model) instance based on the provided model name.

    Args:
        model_name: The name of the model to retrieve. Must be "medium" or "small"

    Returns:
        An instance of OpenAILike configured with the model router settings.
    """
    return _implementation.get_model(model_name)


def get_embedder():
    """
    Get the OpenAIEmbedder instance configured with the appropriate embedding model.

    Returns:
        OpenAIEmbedder: An instance of OpenAIEmbedder configured with the embedding model from settings.
    """
    return _implementation.get_embedder()


def get_client() -> OpenAI:
    """
    Get the model client instance providied by model router.

    Returns:
        A instance of model router client with same usage as openai client
    """
    return _implementation.get_client()


def get_async_client() -> AsyncOpenAI:
    """
    Get the model async client instance providied by model router.

    Returns:
        A instance of model router async client with same usage as async openai client
    """
    return _implementation.get_async_client()
