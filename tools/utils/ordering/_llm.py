from typing import TypeVar, overload

from agno.agent.agent import Agent
from agno.models.groq.groq import Groq
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm
from pydantic import BaseModel

from utils.log import logger

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


@llm(name="get_structured_outputs")
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None = None,
    name: str = "tool",
    openai: bool = False,
) -> T | str | None:
    """
    Makes a call to a language model and returns either a structured or raw response.

    Args:
        system_prompt: The system prompt to provide context to the LLM.
        prompt: The user prompt to send to the LLM.
        response_format: Optional Pydantic model class to structure the response.
        name: Name identifier for the tool, used in agent_id.
        openai: Whether to use OpenAI model instead of Llama.

    Returns:
        If response_format is provided, returns an instance of that model or None on failure.
        If response_format is None, returns the raw string response or None on failure.

    Raises:
        May propagate exceptions from the underlying agent implementation.
    """
    # existing implementation follows…

    model_name = "openai/gpt-oss-120b" if openai else "llama-3.3-70b-versatile"
    client = Groq(id=model_name)

    if response_format:
        system_prompt += """
\n
Structure your response as a valid JSON object, do not include "json" in the beginning
of the response.
"""

    # # Deepseek models works better if everything is passed in the user prompt
    # if "deepseek" in model_name:
    #     prompt = "\n\n".join([system_prompt, prompt])
    #     system_prompt = ""

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

    try:
        response = agent.run(prompt).content
    except Exception as e:
        logger.error(
            f"Error calling LLM {model_name} for {name}: {str(e)}",
            exc_info=True,
            extra={"prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt},
        )
        return None

    LLMObs.annotate(
        input_data=prompt,
        output_data=str(response),
        metadata={"system_prompt": system_prompt},
    )

    return response
