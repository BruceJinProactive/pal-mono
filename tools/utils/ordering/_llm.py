import os
from typing import TypeVar, overload

from agno.agent.agent import Agent
from agno.models.groq.groq import Groq
from anthropic import Anthropic
from anthropic.types import TextBlock, ToolUseBlock
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
    anthropic_client: bool = False,
) -> T | None: ...


@overload
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: None = None,
    name: str = "tool",
    openai: bool = False,
    anthropic_client: bool = False,
) -> str | None: ...


def _call_anthropic_client(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None,
    name: str,
) -> T | str | None:
    """Helper function to call Anthropic's Claude Sonnet 4.5 directly."""
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.error("CLAUDE_API_KEY environment variable is not set")
        return None

    client = Anthropic(api_key=api_key)
    model_name = "claude-sonnet-4-5"

    try:
        if response_format:
            # For structured outputs, use Anthropic's tool calling
            # Convert Pydantic model to tool schema
            schema = response_format.model_json_schema()
            tool_name = "response_tool"

            tools = [
                {
                    "name": tool_name,
                    "description": "Use this tool to provide the structured response",
                    "input_schema": schema,
                }
            ]

            message = client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,  # type: ignore
                tool_choice={"type": "tool", "name": tool_name},
            )

            # Extract the ToolUseBlock from the response
            tool_use_block = None
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    tool_use_block = block
                    break

            if not tool_use_block:
                raise ValueError("No tool use block found in response")

            # Instantiate the Pydantic model from the tool input
            response = response_format(**tool_use_block.input)  # type: ignore
        else:
            # Regular text completion
            message = client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            # Extract text from TextBlock in the content list
            response = ""
            for block in message.content:
                if isinstance(block, TextBlock):
                    response = block.text
                    break

            if not response:
                raise ValueError("No text block found in response")

    except Exception as e:
        logger.error(
            f"Error calling Anthropic {model_name} for {name}: {str(e)}",
            exc_info=True,
            extra={"prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt},
        )
        return None

    LLMObs.annotate(
        input_data=prompt,
        output_data=str(response),
        metadata={"system_prompt": system_prompt, "model": model_name},
    )

    return response


@llm(name="get_structured_outputs")
def llm_call(
    system_prompt: str,
    prompt: str,
    response_format: type[T] | None = None,
    name: str = "tool",
    openai: bool = False,
    anthropic_client: bool = False,
) -> T | str | None:
    """
    Makes a call to a language model and returns either a structured or raw response.

    Args:
        system_prompt: The system prompt to provide context to the LLM.
        prompt: The user prompt to send to the LLM.
        response_format: Optional Pydantic model class to structure the response.
        name: Name identifier for the tool, used in agent_id.
        openai: Whether to use OpenAI model instead of Llama (via Groq).
        anthropic_client: Whether to use Anthropic client directly with Claude Sonnet 4.5.

    Returns:
        If response_format is provided, returns an instance of that model or None on failure.
        If response_format is None, returns the raw string response or None on failure.

    Raises:
        May propagate exceptions from the underlying agent implementation.
    """
    # Use Anthropic client directly with Claude Sonnet 4.5
    if anthropic_client:
        return _call_anthropic_client(system_prompt, prompt, response_format, name)

    # Existing Groq/Agent implementation
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
