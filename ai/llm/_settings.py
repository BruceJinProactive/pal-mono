from pydantic_settings import BaseSettings


class AISettings(BaseSettings):
    """LLM settings that can be set using environment variables.

    Reference: https://pydantic-docs.helpmanual.io/usage/settings/
    """

    gpt_4o_2024_08_06: str = "gpt-4o-2024-08-06"
    gpt_4: str = "gpt-4-turbo"
    gpt_4_vision: str = "gpt-4-turbo"
    gpt_3_5: str = "gpt-3.5-turbo"
    embedding_model: str = "text-embedding-3-small"
    default_max_tokens: int = 1024
    default_temperature: float = 0


# Create AISettings object
ai_settings = AISettings()
