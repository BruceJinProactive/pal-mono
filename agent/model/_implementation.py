import asyncio
import os
import threading
from typing import Any, AsyncIterator, Mapping

import httpx
from agno.models.openai import OpenAIChat
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import task
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from utils.dd import traced
from utils.log import logger

from ._config import ModelOptions

# Module-level singleton for connection reuse with thread-safe initialization
_truefoundry_client: AsyncOpenAI | None = None
_truefoundry_lock: asyncio.Lock | None = None
_lock_init_guard = threading.Lock()  # Thread-safe guard for async lock creation


def _get_lock() -> asyncio.Lock:
    """Get or create the module-level async lock (thread-safe initialization)."""
    global _truefoundry_lock
    if _truefoundry_lock is None:
        with _lock_init_guard:
            if _truefoundry_lock is None:
                _truefoundry_lock = asyncio.Lock()
    return _truefoundry_lock


async def _get_truefoundry_client() -> AsyncOpenAI:
    """
    Get or create a singleton AsyncOpenAI client for TrueFoundry.

    The client is created once and reused across all requests, enabling
    HTTP connection pooling and avoiding repeated TLS handshakes.

    Uses double-checked locking to ensure thread-safe initialization
    while minimizing lock contention after initialization.
    """
    global _truefoundry_client

    # Fast path: client already initialized (no lock needed)
    if _truefoundry_client is not None:
        return _truefoundry_client

    # Slow path: acquire lock and double-check before initializing
    async with _get_lock():
        # Re-check after acquiring lock (another coroutine may have initialized)
        if _truefoundry_client is not None:
            return _truefoundry_client

        api_key = os.getenv("TRUEFOUNDRY_API_KEY")
        if not api_key:
            raise ValueError("TRUEFOUNDRY_API_KEY environment variable not found.")

        base_url = os.getenv("TRUEFOUNDRY_BASE_URL")
        if not base_url:
            raise ValueError("TRUEFOUNDRY_BASE_URL environment variable not found.")

        # Configure custom timeouts for better resilience with connection reuse
        timeout = httpx.Timeout(
            connect=15.0,  # 15s to establish connection (up from 5s default)
            read=600.0,  # 10 min for reading response (LLM can be slow)
            write=10.0,  # 10s for writing request
            pool=10.0,  # 10s waiting for connection from pool
        )

        _truefoundry_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

        return _truefoundry_client


@task(name="LLM Call Default")
async def call_llm_default(
    model_option: ModelOptions, params: Mapping[str, Any]
) -> ChatCompletion:
    """
    Makes a non-streaming LLM request using TrueFoundry gateway.

    Args:
        model_option: Model to use for this request
        params: dict of OpenAI API compatible parameters; model and stream keys will be dropped.

    Returns:
        OpenAI API compatible completions response
    """
    client = await _get_truefoundry_client()

    model_id = os.getenv(model_option.env_key)
    if not model_id:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")

    sanitized_params = {key: value for key, value in params.items() if key != "stream"}
    sanitized_params["model"] = model_id

    LLMObs.annotate(
        input_data=sanitized_params,
        tags={
            "model": model_id,
            "streaming": False,
            "provider": "truefoundry",
        },
    )
    try:
        response = await client.chat.completions.create(
            stream=False, **sanitized_params
        )
        if not isinstance(response, ChatCompletion):
            raise TypeError("Unexpected return type from OpenAI client.")
        return response
    except Exception:
        logger.exception("Chat completion call to TrueFoundry failed.")
        raise


@task(name="LLM Call Stream")
async def call_llm_stream(
    model_option: ModelOptions, params: Mapping[str, Any]
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Makes a streaming LLM request using TrueFoundry gateway.

    Args:
        model_option: Model to use for this request
        params: dict of OpenAI API compatible parameters; model and stream keys will be dropped.

    Returns:
        OpenAI API compatible completions response
    """
    client = await _get_truefoundry_client()

    model_id = os.getenv(model_option.env_key)
    if not model_id:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")

    sanitized_params = {key: value for key, value in params.items() if key != "stream"}
    sanitized_params["model"] = model_id

    LLMObs.annotate(
        tags={
            "model": model_id,
            "streaming": True,
            "provider": "truefoundry",
        }
    )
    try:
        response = await client.chat.completions.create(stream=True, **sanitized_params)
        if not hasattr(response, "__aiter__"):
            raise TypeError("Unexpected return type from OpenAI client.")
        return response
    except Exception:
        logger.exception("Chat completion call to TrueFoundry failed.")
        raise


@traced("Build Agno Model")
def build_agno_model(model_option: ModelOptions) -> OpenAIChat:
    """
    Returns an Agno agent model that calls TrueFoundry gateway to make LLM requests.
    """
    api_key = os.getenv("TRUEFOUNDRY_API_KEY")
    if not api_key:
        raise ValueError("TRUEFOUNDRY_API_KEY environment variable not found.")

    base_url = os.getenv("TRUEFOUNDRY_BASE_URL")
    if not base_url:
        raise ValueError("TRUEFOUNDRY_BASE_URL environment variable not found.")

    # Get model ID from environment variable
    model_id = os.getenv(model_option.env_key)
    if not model_id:
        raise ValueError(f"Environment variable {model_option.env_key} not found.")

    return OpenAIChat(
        id=model_id,
        api_key=api_key,
        base_url=base_url,
    )
