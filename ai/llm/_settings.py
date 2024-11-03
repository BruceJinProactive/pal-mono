from pydantic_settings import BaseSettings


class AISettings(BaseSettings):
    """LLM settings that can be set using environment variables.

    Reference: https://pydantic-docs.helpmanual.io/usage/settings/
    """

    gpt_4o_2024_08_06: str = (
        "gpt-4o-2024-08-06"  # To be removed once adora layer switched to model router
    )
    gpt_4: str = (
        "gpt-4-turbo"  # To be removed once adora layer switched to model router
    )
    gpt_4_vision: str = (
        "gpt-4-turbo"  # To be removed once adora layer switched to model router
    )
    gpt_3_5: str = (
        "gpt-3.5-turbo"  # To be removed once adora layer switched to model router
    )
    standard: str = "standard"
    mini: str = "mini"
    embedding_model: str = "text-embedding-3-small"


# Create AISettings object
ai_settings = AISettings()
