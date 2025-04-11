from typing import TypeVar

from pydantic import BaseModel

RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT = (
    "Identify all the order items of the user's final cart in the chat history."
)

T = TypeVar("T", bound=BaseModel)


def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None = None,
    name: str = "tool",
    reasoning: bool = True,
) -> T | str | None:

    raise NotImplementedError("")
