"""AgentDriver factory for evaluation runs.

Creates the appropriate driver based on driver_mode configuration.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Union

from pal_agents.spec import Spec

from services.eval_service._http_voice_driver import HttpVoiceDriver
from services.eval_service._inprocess_driver import InProcessDriver
from utils.log import logger

AgentDriver = Union[InProcessDriver, HttpVoiceDriver]

# ``driver_mode`` values:
#
# - ``"http_voice"`` — HTTP-over-ASGI driver that speaks the same
#   public contract the LiveKit agent worker uses (/internal/voice/init,
#   /chat/completions streaming, /internal/voice/end-call). Recommended
#   for new evals: the driver only depends on the HTTP boundary, not on
#   internal service modules, so refactors inside ``services/`` or
#   ``db/`` cannot silently break the eval surface.
#
# - ``"http"`` — legacy in-process driver (:class:`InProcessDriver`) that
#   calls :func:`services.message_service.get_chat_response_async`
#   directly. Historical misnomer — nothing goes over HTTP despite the
#   name. Kept for backward compatibility with existing scenarios;
#   prefer ``"http_voice"`` for new work.
#
# - ``"direct"`` — not implemented.


def create_driver(
    driver_mode: str,
    project_identifier: str,
    channel: str = "api",
    scenario_id: str | None = None,
    customer_phone: str | None = None,
    spec_modifier: Callable[[Spec], None] | None = None,
) -> AgentDriver:
    """Create an AgentDriver for the given mode.

    Each call generates a unique ``sender_identifier`` / ``call_id`` so
    the chat service creates a fresh conversation per scenario,
    preventing tool-call bleed between scenarios.

    Args:
        driver_mode: See module docstring. One of ``"http_voice"``,
            ``"http"`` (legacy in-process), or ``"direct"`` (NYI).
        project_identifier: Channel-specific identifier for routing
            messages. For ``"http_voice"`` this is the dialled number
            registered at ``voice:<project_identifier>``.
        channel: Channel type (e.g. "api", "voice"). Ignored by
            ``"http_voice"`` (always VOICE by construction). Defaults to
            ``"api"``.
        scenario_id: Optional scenario ID included in the sender /
            call_id for traceability.
        customer_phone: Optional phone number. For ``"http_voice"`` this
            becomes the ``caller_number``; for ``"http"`` it is injected
            into ``RuntimeContext``.
        spec_modifier: Optional ``Spec`` mutator. Only honoured by
            ``"http"`` (InProcessDriver); the HTTP-over-ASGI path has no
            hook for it. See ``_http_voice_driver.py`` docstring.

    Returns:
        An AgentDriver instance.

    Raises:
        ValueError: If ``driver_mode`` is not recognized.
    """
    if driver_mode == "http_voice":
        # Resolve the live FastAPI app via importlib to avoid a static
        # ``services -> api`` layering violation. The ``http_voice`` driver
        # deliberately hits the HTTP boundary via ASGITransport, which
        # requires the app object. Using ``importlib`` makes this a runtime
        # DI seam that import-linter tolerates while keeping everything else
        # in the service clean. Callers that want to inject a non-default
        # app (e.g. tests) should construct :class:`HttpVoiceDriver` directly.
        import importlib

        _api_main = importlib.import_module("api.main")
        app = _api_main.app

        caller_number = customer_phone or "+15550000000"
        logger.info(
            "Creating HttpVoiceDriver",
            extra={
                "project": project_identifier,
                "caller_number_last4": caller_number[-4:],
                "scenario_id": scenario_id,
            },
        )
        return HttpVoiceDriver(
            app=app,
            recipient_identifier=project_identifier,
            caller_number=caller_number,
            scenario_id=scenario_id,
        )

    if driver_mode == "http":
        unique_id = uuid.uuid4().hex[:12]
        sender = f"eval-{scenario_id or 'anon'}-{unique_id}@test.com"
        logger.info(
            "Creating InProcessDriver",
            extra={
                "project": project_identifier,
                "channel": channel,
                "sender": sender,
            },
        )
        return InProcessDriver(
            recipient_identifier=project_identifier,
            sender_identifier=sender,
            channel=channel,
            customer_phone=customer_phone,
            spec_modifier=spec_modifier,
        )

    if driver_mode == "direct":
        raise NotImplementedError(
            "DirectDriver requires agent Spec construction — not yet wired. "
            "Use driver_mode='http_voice' (recommended) or 'http' (legacy)."
        )

    raise ValueError(
        f"Unknown driver_mode: {driver_mode!r}. "
        "Expected 'http_voice', 'http', or 'direct'. Voice LiveKit mode "
        "is handled by _run_scenario_for_mode."
    )
