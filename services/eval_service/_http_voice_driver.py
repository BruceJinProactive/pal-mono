"""HTTP-over-ASGI eval driver — calls pal-mono's public HTTP contract.

Unlike :class:`~services.eval_service._inprocess_driver.InProcessDriver`,
which reaches into ``services.message_service`` directly, this driver
speaks only to the FastAPI app via its HTTP routes. It is the
text-transport analogue of a LiveKit voice call:

    init   → POST /v1/internal/voice/init
    turn N → POST /v1/chat/completions  (streamed)
    ...
    teardown → POST /v1/internal/voice/end-call

The transport is ``httpx.AsyncClient(transport=ASGITransport(app=...))``
so everything runs in-process with no real network — but the code path
exercised is the *same* one that the LiveKit agent worker exercises in
production. Refactors inside ``services/`` or ``db/`` cannot silently
break the eval surface: if the HTTP contract changes, the driver sees
it immediately.

Safety: the driver flags the Conversation as a test run via
``testing=True`` in the ``/internal/voice/init`` payload. Downstream
spec construction in ``services.message_service`` auto-applies
:func:`utils.eval_safety.apply_eval_safety`, which enforces
``toast.submit_orders=False`` and ``adora.force_payment_link=True`` for
every turn of the scenario — the same guarantees ``InProcessDriver``
gets from its ``spec_modifier=apply_eval_safety`` default. No driver
spec-modifier hook is required because the safety is keyed on the
persisted ``Conversation.is_test`` flag, which every caller path
(InProcessDriver, HttpVoiceDriver, real-voice LiveKit) sets uniformly
via ``metadata.testing=True``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI
from httpx import ASGITransport
from pal_agents.evals.drivers.protocol import ConversationTurn, TurnResult

from utils.log import logger

_INIT_PATH = "/v1/internal/voice/init"
_CHAT_PATH = "/v1/chat/completions"
_END_CALL_PATH = "/v1/internal/voice/end-call"

# Fallback values used only when the scenario doesn't carry a caller phone.
_DEFAULT_CALLER_NUMBER = "+15550000000"


class HttpVoiceDriver:
    """Eval driver that talks to pal-mono over its HTTP contract.

    One scenario = one synthetic ``call_id`` = one ``Conversation`` row
    (guaranteed by the voice-channel DB plumbing that keys lookup on
    ``call_id``). The driver does not import ``services.*`` or ``db.*``
    beyond type stubs.

    Lifecycle:

    1. ``__init__`` stores configuration; no network yet.
    2. First ``send_turn`` lazily calls ``POST /internal/voice/init`` to
       create the Conversation + PhoneCall rows, then streams the first
       chat completion.
    3. Subsequent ``send_turn`` calls stream chat completions only.
    4. ``aclose`` (invoked by the runner in a ``finally`` block) calls
       ``POST /internal/voice/end-call`` and populates
       ``last_conversation_id`` from the response so the runner can
       extract tool calls.

    Attributes:
        last_conversation_id: Conversation UUID as a string, populated on
            ``aclose``. ``None`` until teardown succeeds.
        call_id: Synthetic call id minted per driver instance. Stable for
            the scenario's lifetime.
    """

    def __init__(
        self,
        *,
        app: FastAPI,
        recipient_identifier: str,
        caller_number: str = _DEFAULT_CALLER_NUMBER,
        scenario_id: str | None = None,
        base_url: str = "http://eval.local",
        timeout_s: float = 60.0,
    ) -> None:
        """Construct a driver for a single eval scenario.

        Args:
            app: The FastAPI application to dispatch against. Normally
                ``api.main.app``. Accepting the app as an explicit
                dependency keeps the driver testable (tests can pass a
                mock app).
            recipient_identifier: Dialled number, e.g. ``"+14155551212"``.
                Must resolve to a project registered at
                ``voice:<recipient_identifier>``.
            caller_number: Caller-side identifier. Defaults to a
                placeholder; scenarios that care about caller phone
                should pass their own.
            scenario_id: Optional scenario id; embedded in the ``call_id``
                for traceability in logs and Langfuse tags.
            base_url: Base URL used by the ASGI transport. Only affects
                the ``Host`` header; the actual routing is via the app.
            timeout_s: Per-request timeout. Streaming responses inherit
                this for the initial connect.
        """
        self._app = app
        self._recipient_identifier = recipient_identifier
        self._caller_number = caller_number
        self._scenario_id = scenario_id
        self._base_url = base_url
        self._timeout_s = timeout_s

        suffix = scenario_id or "anon"
        self.call_id = f"eval-{suffix[:16]}-{uuid.uuid4().hex[:8]}"

        self._client: httpx.AsyncClient | None = None
        self._initialized = False
        self._closed = False
        self._conversation_history: list[dict[str, str]] = []
        self.last_conversation_id: str | None = None

    # ------------------------------------------------------------------
    # AgentDriver protocol
    # ------------------------------------------------------------------

    async def send_turn(
        self,
        message: str,
        conversation_history: list[ConversationTurn],
    ) -> TurnResult:
        """Send a user turn and return the accumulated assistant reply.

        The ``conversation_history`` argument from the runner is ignored
        because the server manages its own history via the DB keyed on
        ``call_id``.
        """
        if self._closed:
            raise RuntimeError("HttpVoiceDriver.send_turn called after aclose()")

        await self._ensure_initialized()
        assert self._client is not None

        caller_info = {
            "sender_identifier": self._caller_number,
            "recipient_identifier": self._recipient_identifier,
            "call_id": self.call_id,
        }
        payload = {
            "model": json.dumps(caller_info),
            "messages": [{"role": "user", "content": message}],
            "stream": True,
        }

        content = await self._consume_chat_stream(payload)

        # Track for the end-call conversation replay.
        self._conversation_history.append({"role": "user", "content": message})
        self._conversation_history.append({"role": "assistant", "content": content})

        return TurnResult(content=content)

    async def aclose(self) -> None:
        """Finalize the call via ``POST /internal/voice/end-call``.

        Idempotent — safe to call even if ``send_turn`` was never invoked.
        Populates ``last_conversation_id`` from the response so the
        runner's tool-call extractor can query the DB by conversation.
        """
        if self._closed:
            return
        self._closed = True

        try:
            if self._initialized and self._client is not None:
                payload = {
                    "call_id": self.call_id,
                    "caller_number": self._caller_number,
                    "dialed_number": self._recipient_identifier,
                    "duration_seconds": 0.0,
                    "conversation": self._conversation_history,
                    "close_reason": "eval_complete",
                }
                response = await self._client.post(_END_CALL_PATH, json=payload)
                # Tolerate a non-2xx end-call: we still want to extract
                # tool calls from the (already-persisted) conversation if
                # we can. Log loudly but don't raise.
                if response.is_success:
                    data = response.json()
                    conversation_id = data.get("conversation_id")
                    if conversation_id:
                        self.last_conversation_id = str(conversation_id)
                else:
                    logger.warning(
                        "HttpVoiceDriver end-call returned %s: %s",
                        response.status_code,
                        response.text[:500],
                        extra={"call_id": self.call_id},
                    )
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        self._client = httpx.AsyncClient(
            transport=ASGITransport(app=self._app),
            base_url=self._base_url,
            timeout=self._timeout_s,
        )

        init_payload = {
            "caller_number": self._caller_number,
            "dialed_number": self._recipient_identifier,
            "call_id": self.call_id,
            # Flag the Conversation as a test run so downstream spec
            # construction auto-applies ``apply_eval_safety``. This is
            # the structural equivalent of ``InProcessDriver``'s
            # ``spec_modifier=apply_eval_safety`` default.
            "testing": True,
        }
        response = await self._client.post(_INIT_PATH, json=init_payload)
        if not response.is_success:
            # Close the client so we don't leak connections if init fails.
            await self._client.aclose()
            self._client = None
            raise RuntimeError(
                f"voice /init failed: HTTP {response.status_code} "
                f"{response.text[:500]}"
            )

        self._initialized = True
        logger.info(
            "HttpVoiceDriver initialized",
            extra={
                "call_id": self.call_id,
                "recipient_identifier": self._recipient_identifier,
                "scenario_id": self._scenario_id,
            },
        )

    async def _consume_chat_stream(self, payload: dict[str, Any]) -> str:
        """POST to /chat/completions and accumulate streamed content.

        The endpoint returns an SSE-style stream of ``data: {...}``
        lines. Each JSON payload is an OpenAI-compatible chat-completion
        chunk. The assistant reply for this turn is the concatenation of
        all ``choices[0].delta.content`` strings, stopping when the
        server sends ``data: [DONE]`` or the stream closes.
        """
        assert self._client is not None

        parts: list[str] = []
        async with self._client.stream("POST", _CHAT_PATH, json=payload) as response:
            if not response.is_success:
                body = await response.aread()
                raise RuntimeError(
                    f"chat /completions failed: HTTP {response.status_code} "
                    f"{body.decode('utf-8', errors='replace')[:500]}"
                )

            async for piece in _parse_sse_content(response.aiter_lines()):
                parts.append(piece)

        return "".join(parts)


async def _parse_sse_content(
    lines: AsyncIterator[str],
) -> AsyncIterator[str]:
    """Yield ``choices[0].delta.content`` strings from an SSE stream.

    Tolerant to blank lines, comments, and occasional non-JSON frames.
    Stops on ``data: [DONE]`` or when the iterator is exhausted.
    """
    async for raw in lines:
        if not raw:
            continue
        if not raw.startswith("data:"):
            # Comments / keepalives / non-data frames.
            continue
        data = raw[len("data:") :].strip()
        if not data:
            continue
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            logger.debug("HttpVoiceDriver: skipping non-JSON SSE frame: %r", data[:200])
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content:
            yield content
