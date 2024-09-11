from . import _implementation, _settings


def get_llm(llm_name: _implementation.LLM = _implementation.LLM.ROUTER):
    """
    Get the appropriate LLM (Large Language Model) instance based on the provided LLM name.

    Args:
        llm_name (LLM): The name of the LLM to retrieve. Must be one of the LLM enum values.

    Returns:
        An instance of OpenAIChat or OpenAILike configured with the appropriate settings.

    Raises:
        ValueError: If an invalid LLM name is provided.
    """
    return _implementation.get_llm(llm_name)


def get_embedder():
    """
    Get the OpenAIEmbedder instance configured with the appropriate embedding model.

    Returns:
        OpenAIEmbedder: An instance of OpenAIEmbedder configured with the embedding model from settings.
    """
    return _implementation.get_embedder()


LLM = _implementation.LLM  # TODO: Remove this after fully migrate to model router

ai_settings = (
    _settings.ai_settings
)  # TODO: Remove this after fully migrate to model router


__all__ = ["get_llm", "ai_settings"]
