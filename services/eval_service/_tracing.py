"""Langfuse tracing helpers for eval runs.

Provides a per-scenario trace boundary so that each scenario ("test case")
produces exactly one Langfuse trace, with every turn nested underneath as a
child observation.

Why this module exists
----------------------
The service is booted via ``opentelemetry-instrument`` (see
``pyproject.toml`` — ``opentelemetry-distro`` + ``opentelemetry-instrumentation-fastapi``),
so every FastAPI handler runs inside an auto-created root span. The eval
runner kicks off its work via ``asyncio.create_task(_run_eval_background(...))``
from the POST /evals/runs handler, and ``asyncio.create_task`` snapshots the
current ``contextvars`` — including the OTel span context — into the
background task. That context is still "active" after the originating HTTP
request returns, so every subsequent Langfuse observation created inside the
eval (which is OTel-backed under Langfuse SDK v4) becomes a child of that
leaked trace. Net effect without this helper: **all scenarios and all turns
in one eval run share a single Langfuse trace_id**.

``scenario_trace_boundary`` fixes that by (1) attaching an empty OTel
context at the scenario boundary so the leaked parent is no longer visible,
and (2) opening an explicit "Eval Scenario" root observation that every turn
of the scenario nests beneath. The result is one trace per scenario,
tagged/filterable by ``eval_run_id`` and ``scenario_id``.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager

from langfuse import get_client, propagate_attributes
from opentelemetry import context as otel_context


@contextmanager
def scenario_trace_boundary(
    *,
    eval_run_id: uuid.UUID,
    scenario_id: str,
) -> Generator[None, None, None]:
    """Start a fresh Langfuse trace scoped to one eval scenario.

    Detaches any inherited OTel context (see module docstring) and opens a
    root "Eval Scenario" observation. All observations created inside the
    ``with`` block — including per-turn ``langfuse_message_span`` spans
    inside ``get_chat_response_async`` — become children of this scenario
    span and share its ``trace_id``.

    Adds ``eval_run:<uuid>`` and ``scenario:<id>`` tags plus an
    ``eval_run_id`` metadata field via ``propagate_attributes`` so the
    resulting trace is filterable in the Langfuse UI.

    Args:
        eval_run_id: The parent eval run's UUID.
        scenario_id: The scenario's string identifier.
    """
    # 1. Strip the FastAPI request's leaked trace context.
    token = otel_context.attach(otel_context.Context())
    try:
        lf = get_client()
        # 2. Open an explicit scenario-level root span; child turns nest here.
        with (
            lf.start_as_current_observation(
                name="Eval Scenario",
                as_type="span",
                input={"scenario_id": scenario_id},
            ),
            propagate_attributes(
                tags=[
                    f"eval_run:{eval_run_id}",
                    f"scenario:{scenario_id}",
                ],
                metadata={
                    "eval_run_id": str(eval_run_id),
                    "scenario_id": scenario_id,
                },
            ),
        ):
            yield
    finally:
        otel_context.detach(token)
