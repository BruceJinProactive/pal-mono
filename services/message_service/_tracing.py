"""Langfuse tracing helpers for message_service.

Provides a context manager that creates a root Langfuse observation with
proper trace attributes (session_id, user_id, tags, metadata).
"""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from langfuse import get_client, propagate_attributes


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
    lf = get_client()
    with (
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
