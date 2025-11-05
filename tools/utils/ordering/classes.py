from enum import Enum

from pydantic import BaseModel, Field


class ApiProvider(str, Enum):
    """Enum for different API providers"""

    OLO = "olo"
    ADORA = "adora"
    TOAST = "toast"


class GenericHubResponse(BaseModel):
    """Generic response class that matches all three API response formats"""

    status: int
    reason: str
    decoded_body: str


class HttpMethod(str, Enum):
    """HTTP methods supported by the APIs"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class SubQueries(BaseModel):
    queries: list[str] = Field(
        description=(
            "Decompose the chat history into individual order items. For example,"
            "If the chat history is 'I would like to order a pizza with extra cheese "
            "and pickles, burger, and salad, for takeout.' The return would be ['pizza with extra cheese and pickles', "
            "'burger', 'salad']"
        ),
    )


class OrderConstructionModel(str, Enum):
    """
    Enum for order construction LLM client selection.
    """

    LLAMA = "llama"  # Default - Llama 3.3 70B via Groq
    OPENAI = "openai"  # OpenAI GPT-OSS 120B via Groq
    CLAUDE = "claude"  # Anthropic Claude Sonnet 4.5
