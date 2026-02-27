from typing import TypeVar, overload

from agno.agent.agent import Agent
from agno.models.groq.groq import Groq
from ddtrace.llmobs.decorators import llm
from pydantic import BaseModel

from utils.dd import safe_annotate

T = TypeVar("T", bound=BaseModel)


@overload
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T],
    name: str = "tool",
    openai: bool = False,
) -> T | None: ...


@overload
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: None = None,
    name: str = "tool",
    openai: bool = False,
) -> str | None: ...


# This LLM is brought from Adora. Let's do a refactor to merge them.
@llm(name="get_structured_outputs")
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None = None,
    name: str = "tool",
    openai: bool = False,
) -> T | str | None:

    model_name = "openai/gpt-oss-120b" if openai else "llama-3.3-70b-versatile"
    client = Groq(id=model_name)

    if response_format:
        system_prompt += """\n\nStructure your response as a valid JSON object, do not include "json" in the beginning
of the response. Do not include newline characters in the returned JSON object.
"""

    # OpenAI models work better with separate system and user prompts
    # No special handling needed for OpenAI models

    agent = Agent(
        model=client,
        agent_id=f"ordering-tools/{name}",
        session_id="test-session",
        add_history_to_messages=True,
        knowledge=None,
        response_model=response_format,
        system_message=system_prompt,
        num_history_responses=0,
        search_knowledge=False,
    )

    response = agent.run(prompt).content

    safe_annotate(
        input_data=prompt,
        output_data=str(response),
        metadata={"system_prompt": system_prompt},
    )

    return response
