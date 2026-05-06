"""Tests for services.eval_service._tracing.

Covers ``scenario_trace_boundary``: OTel context isolation (so scenarios do
not share ``trace_id`` with each other or with the originating HTTP request's
auto-instrumented span) and correct Langfuse attribute propagation
(scenario-level root observation, filterable tags, metadata).

These tests use real ``opentelemetry`` for the context-isolation check
because the whole point of the helper is to interact correctly with the
real OTel context machinery. Langfuse is mocked because ``get_client()``
touches module-level state we don't want to exercise here.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from services.eval_service._tracing import scenario_trace_boundary

TRACING_MODULE = "services.eval_service._tracing"


@pytest.fixture(autouse=True)
def _install_real_tracer_provider() -> None:
    """Install a real ``TracerProvider`` for the duration of these tests.

    The default global provider in a pytest environment is a ``ProxyTracerProvider``
    whose spans yield ``trace_id=0`` (the INVALID span). That makes it impossible
    to distinguish "leaked parent span" from "empty context" — both would look
    like ``trace_id=0`` and the isolation assertions below would pass trivially.
    Installing a real SDK provider gives spans real trace ids so we can verify
    the boundary actually detaches the context.

    We do *not* reset the global provider after the test: OTel's
    ``trace.set_tracer_provider`` warns on overwrite, and leaving a real
    provider in place is harmless for the rest of the suite.
    """
    current = trace.get_tracer_provider()
    if not isinstance(current, TracerProvider):
        trace.set_tracer_provider(TracerProvider())


def _make_mock_langfuse_client(
    *,
    observations: list[dict[str, Any]],
) -> MagicMock:
    """Return a Langfuse client mock that records ``start_as_current_observation``.

    Each call appends ``{"name": ..., "as_type": ..., "input": ...}`` to
    ``observations`` so assertions can inspect them in order.
    """
    client = MagicMock()

    @contextmanager
    def _start_as_current_observation(**kwargs: Any):
        observations.append(kwargs)
        yield MagicMock()

    client.start_as_current_observation = _start_as_current_observation
    return client


@contextmanager
def _mock_propagate_attributes(calls: list[dict[str, Any]]):
    """Context-manager factory that records every ``propagate_attributes`` call."""

    @contextmanager
    def _recorder(**kwargs: Any):
        calls.append(kwargs)
        yield

    yield _recorder


# ---------------------------------------------------------------------------
# Langfuse attribute propagation
# ---------------------------------------------------------------------------


class TestLangfuseAttributes:
    """``scenario_trace_boundary`` must open the scenario root span with the
    correct name/input and attach filterable tags + metadata via
    ``propagate_attributes``."""

    def test_opens_scenario_root_observation_with_input(self) -> None:
        observations: list[dict[str, Any]] = []
        prop_calls: list[dict[str, Any]] = []
        client = _make_mock_langfuse_client(observations=observations)

        eval_run_id = uuid.uuid4()
        scenario_id = "ordering/sonnys_bbq_001"

        with (
            patch(f"{TRACING_MODULE}.get_client", return_value=client),
            _mock_propagate_attributes(prop_calls) as recorder,
            patch(f"{TRACING_MODULE}.propagate_attributes", recorder),
        ):
            with scenario_trace_boundary(
                eval_run_id=eval_run_id, scenario_id=scenario_id
            ):
                pass

        assert len(observations) == 1, "exactly one scenario root observation"
        obs = observations[0]
        assert obs["name"] == "Eval Scenario"
        assert obs["as_type"] == "span"
        assert obs["input"] == {"scenario_id": scenario_id}

    def test_propagates_filterable_tags_and_metadata(self) -> None:
        observations: list[dict[str, Any]] = []
        prop_calls: list[dict[str, Any]] = []
        client = _make_mock_langfuse_client(observations=observations)

        eval_run_id = uuid.uuid4()
        scenario_id = "generic/smoke_001"

        with (
            patch(f"{TRACING_MODULE}.get_client", return_value=client),
            _mock_propagate_attributes(prop_calls) as recorder,
            patch(f"{TRACING_MODULE}.propagate_attributes", recorder),
        ):
            with scenario_trace_boundary(
                eval_run_id=eval_run_id, scenario_id=scenario_id
            ):
                pass

        assert len(prop_calls) == 1
        call = prop_calls[0]
        assert set(call["tags"]) == {
            f"eval_run:{eval_run_id}",
            f"scenario:{scenario_id}",
        }
        assert call["metadata"] == {
            "eval_run_id": str(eval_run_id),
            "scenario_id": scenario_id,
        }

    def test_yields_control_to_caller(self) -> None:
        """Regression: body must execute between enter and exit."""
        observations: list[dict[str, Any]] = []
        prop_calls: list[dict[str, Any]] = []
        client = _make_mock_langfuse_client(observations=observations)

        ran = False
        with (
            patch(f"{TRACING_MODULE}.get_client", return_value=client),
            _mock_propagate_attributes(prop_calls) as recorder,
            patch(f"{TRACING_MODULE}.propagate_attributes", recorder),
        ):
            with scenario_trace_boundary(eval_run_id=uuid.uuid4(), scenario_id="x"):
                ran = True

        assert ran is True


# ---------------------------------------------------------------------------
# OTel context isolation — the core correctness property
# ---------------------------------------------------------------------------


class TestOtelContextIsolation:
    """The helper must strip any inherited OTel span context so that
    observations opened inside the boundary do not share a ``trace_id``
    with the leaked parent (e.g. the FastAPI request span that
    ``asyncio.create_task`` copied in).

    We verify this by starting a real OTel span *outside* the boundary,
    then checking that the current context *inside* the boundary has no
    active span — proving that the call-site's ``lf.start_as_current_observation``
    will create a brand-new root trace rather than a child of the leaked
    parent.
    """

    def test_strips_inherited_otel_span_context(self) -> None:
        observations: list[dict[str, Any]] = []
        prop_calls: list[dict[str, Any]] = []

        # Use a Langfuse stub that doesn't itself open an OTel span, so we
        # can observe the raw context state inside the boundary.
        client = _make_mock_langfuse_client(observations=observations)

        tracer = trace.get_tracer("test.eval_tracing")
        observed_inside_trace_ids: list[int] = []

        # Simulate a leaked parent span (the FastAPI request context).
        with tracer.start_as_current_span("simulated-fastapi-request") as parent:
            parent_ctx = parent.get_span_context()
            assert parent_ctx.trace_id != 0, "sanity: parent has a real trace_id"

            with (
                patch(f"{TRACING_MODULE}.get_client", return_value=client),
                _mock_propagate_attributes(prop_calls) as recorder,
                patch(f"{TRACING_MODULE}.propagate_attributes", recorder),
            ):
                with scenario_trace_boundary(
                    eval_run_id=uuid.uuid4(), scenario_id="iso-1"
                ):
                    current = trace.get_current_span().get_span_context()
                    observed_inside_trace_ids.append(current.trace_id)

            # After exiting the boundary, the leaked parent must still be
            # the active span — the helper must not leak its own detach
            # out to the caller's scope.
            after = trace.get_current_span().get_span_context()
            assert (
                after.trace_id == parent_ctx.trace_id
            ), "context must be restored on exit"

        # Inside the boundary, no active parent span should be visible
        # (trace_id == 0 means the INVALID span, i.e. empty context).
        assert observed_inside_trace_ids == [0], (
            "expected empty OTel context inside boundary, got "
            f"{observed_inside_trace_ids!r}"
        )

    def test_sibling_scenarios_see_independent_context(self) -> None:
        """Two scenarios entered sequentially under the same leaked parent
        must each see an empty context — the first scenario's exit must
        not poison the second."""
        observations: list[dict[str, Any]] = []
        prop_calls: list[dict[str, Any]] = []
        client = _make_mock_langfuse_client(observations=observations)

        tracer = trace.get_tracer("test.eval_tracing")
        inside_ids: list[int] = []

        with tracer.start_as_current_span("simulated-fastapi-request"):
            for sid in ("scenario-a", "scenario-b"):
                with (
                    patch(f"{TRACING_MODULE}.get_client", return_value=client),
                    _mock_propagate_attributes(prop_calls) as recorder,
                    patch(f"{TRACING_MODULE}.propagate_attributes", recorder),
                ):
                    with scenario_trace_boundary(
                        eval_run_id=uuid.uuid4(), scenario_id=sid
                    ):
                        inside_ids.append(
                            trace.get_current_span().get_span_context().trace_id
                        )

        assert inside_ids == [
            0,
            0,
        ], "each scenario must see an empty OTel context independently"

    def test_detaches_context_even_on_exception(self) -> None:
        """The ``finally`` branch must restore the OTel context even if
        the body raises."""
        observations: list[dict[str, Any]] = []
        prop_calls: list[dict[str, Any]] = []
        client = _make_mock_langfuse_client(observations=observations)

        tracer = trace.get_tracer("test.eval_tracing")

        with tracer.start_as_current_span("simulated-fastapi-request") as parent:
            parent_trace_id = parent.get_span_context().trace_id

            with (
                patch(f"{TRACING_MODULE}.get_client", return_value=client),
                _mock_propagate_attributes(prop_calls) as recorder,
                patch(f"{TRACING_MODULE}.propagate_attributes", recorder),
            ):
                with pytest.raises(RuntimeError, match="scenario boom"):
                    with scenario_trace_boundary(
                        eval_run_id=uuid.uuid4(), scenario_id="err-1"
                    ):
                        raise RuntimeError("scenario boom")

            after = trace.get_current_span().get_span_context()
            assert (
                after.trace_id == parent_trace_id
            ), "context must be restored after body raises"
