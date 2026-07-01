"""Langfuse tracing helpers for message_service.

Provides a context manager that creates a root Langfuse observation with
proper trace attributes (session_id, user_id, tags, metadata).
"""

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse, get_client, propagate_attributes
from langfuse._client.get_client import _set_current_public_key

_voice_langfuse_client: Langfuse | None = None


def _get_voice_langfuse_client() -> tuple[Any, str | None]:
    global _voice_langfuse_client

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY") or None
    if public_key is None:
        return get_client(), None

    if _voice_langfuse_client is None:
        _voice_langfuse_client = Langfuse(public_key=public_key)

    return _voice_langfuse_client, public_key


@contextmanager
def langfuse_message_span(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    account_name: str,
    project_name: str,
    channel: str,
) -> Generator[Any, None, None]:
    """Create a Langfuse root observation with propagated trace attributes.

    Usage::

        with langfuse_message_span(...) as lf:
            lf.set_current_trace_io(input={"content": text})
            result = await run_agent(...)
            lf.set_current_trace_io(output={"content": result.content})
    """
    lf, public_key = _get_voice_langfuse_client()
    with (
        _set_current_public_key(public_key),
        lf.start_as_current_observation(
            name="Message Service Processing",
            as_type="span",
        ),
        propagate_attributes(
            trace_name="Pal Agent Request",
            session_id=str(conversation_id),
            user_id=str(user_id),
            tags=[
                f"agent_id:{agent_id}",
                f"account:{account_name}",
                f"channel:{channel}",
            ],
            metadata={
                "project_name": project_name,
                "account_name": account_name,
            },
        ),
    ):
        yield lf
