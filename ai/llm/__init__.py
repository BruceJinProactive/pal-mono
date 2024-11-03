from . import _implementation, _settings


def get_model(model_name: str = _settings.ai_settings.standard):
    """
    Get the appropriate LLM (Large Language Model) instance based on the provided model name.

    Args:
        model_name: The name of the model to retrieve. Must be "standard" or "mini"

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


def get_client():
    """
    Get the model client instance providied by model router.

    Returns:
        A instance of model router client with same usage as openai client
    """
    return _implementation.get_client()


OutputModel = _implementation.OutputModel

ai_settings = (
    _settings.ai_settings
)  # TODO: Remove this after fully migrate to model router


__all__ = ["get_model", "ai_settings"]
