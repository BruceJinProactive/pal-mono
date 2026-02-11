import asyncio
import datetime
import os
import threading
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Dict, Optional, cast

from datadog import DogStatsd  # pyright: ignore[reportPrivateImportUsage]
from ddtrace import tracer  # pyright: ignore[reportPrivateImportUsage]
from ddtrace import patch
from ddtrace.llmobs import LLMObs

from utils.log import logger

# Context variable to track testing mode for current request
# When True, all Datadog logging/tracing is disabled for the request
_testing_mode: ContextVar[bool] = ContextVar("testing_mode", default=False)
_llmobs_lock = threading.Lock()
_llmobs_initialized = False
_llmobs_enabled = False

# -----------------------------------------------------------------------------
# openai-agents / ddtrace compatibility context
# -----------------------------------------------------------------------------
# We run openai-agents>=0.8.3. In this SDK line, turn execution moved from
# private Runner/AgentRunner methods to module-level functions in agents.run.
# Datadog ddtrace<=4.1.0 still attempts to patch removed private methods, which
# can raise AttributeError during LLMObs initialization and fail user requests.
#
# This file uses a local compatibility patch that:
# 1) Initializes Datadog openai_agents integration objects manually
# 2) Wraps the module-level entry points used by openai-agents>=0.8.3
# 3) Keeps patching failure non-fatal so message handling continues
# 4) Cleans up partial patch state on errors (flags, pins, processors)
# -----------------------------------------------------------------------------

# `tag_agent_manifest` resolves the agent from args/kwargs.
# For run_single_turn, the kwarg is `agent` and positional index is 0.
_RUN_SINGLE_TURN_AGENT_INDEX = 0
# For start_streaming, the kwarg is `starting_agent` (mapped to `agent`) and
# the positional index of starting_agent is 2 in openai-agents>=0.8.3.
_START_STREAMING_AGENT_INDEX = 2


def set_testing_mode(testing: bool) -> None:
    """Set testing mode for current request context."""
    _testing_mode.set(testing)


def is_testing_mode() -> bool:
    """Check if current request is in testing mode."""
    return _testing_mode.get()


def _openai_agents_wrapper(agent_index: int) -> Any:
    """
    Build a Datadog wrapper for openai-agents turn execution paths.

    The wrapper function signature must match Datadog's wrapt callback contract:
    (module, pin, wrapped, instance, args, kwargs).
    """
    from ddtrace.contrib.internal.trace_utils_async import with_traced_module

    # ddtrace 3.11 exposes only `with_traced_module` in internal async utils.
    with_traced_module_async = with_traced_module

    @with_traced_module_async
    async def _wrapped_openai_agents_turn(agents, pin, func, instance, args, kwargs):
        current_span = pin.tracer.current_span()
        result = await func(*args, **kwargs)

        integration = getattr(agents, "_datadog_integration", None)
        if integration is None or current_span is None:
            return result

        # openai-agents>=0.8.3 uses `starting_agent` in streamed execution.
        tag_kwargs = kwargs
        if "agent" not in kwargs and "starting_agent" in kwargs:
            tag_kwargs = dict(kwargs)
            tag_kwargs["agent"] = kwargs["starting_agent"]

        try:
            integration.tag_agent_manifest(current_span, args, tag_kwargs, agent_index)
        except Exception:
            logger.debug("Failed to tag openai-agents manifest", exc_info=True)

        return result

    return cast(Any, _wrapped_openai_agents_turn)


def _patch_openai_agents_integration() -> bool:
    """
    Patch Datadog's openai_agents integration with compatibility for agents>=0.8.3.

    ddtrace<=4.1.0 attempts to wrap AgentRunner private methods that no longer exist
    in openai-agents 0.8.x, which raises AttributeError during patching.
    """
    # Step 1: Import Datadog/OpenAI internals required to wire the integration.
    # Any import failure should degrade gracefully and not break request handling.
    try:
        import agents
        from agents.tracing import (
            add_trace_processor,
            get_trace_provider,
            set_trace_processors,
        )
        from ddtrace import config
        from ddtrace._trace.pin import Pin  # type: ignore[reportPrivateUsage]
        from ddtrace.contrib.internal.openai_agents.processor import (
            LLMObsTraceProcessor,
        )
        from ddtrace.contrib.internal.trace_utils import wrap
        from ddtrace.internal.utils.version import parse_version
        from ddtrace.llmobs._integrations.openai_agents import OpenAIAgentsIntegration
    except Exception:
        logger.info(
            "Skipping ddtrace LLM integration patch",
            extra={"integration": "openai_agents"},
            exc_info=True,
        )
        return False

    if getattr(agents, "_datadog_patch", False):
        return True

    # Step 2: Enforce the only SDK line we support in this code path.
    # This PR intentionally removed backward compatibility for <0.8.3.
    openai_agents_version = parse_version(getattr(agents.version, "__version__", ""))
    if openai_agents_version < (0, 8, 3):
        logger.warning(
            "openai_agents integration requires openai-agents>=0.8.3",
            extra={"detected_version": str(openai_agents_version)},
        )
        return False

    # Step 3: Snapshot current processors so we can restore them if patching fails
    # after mutation. openai-agents doesn't expose a public getter, so we read the
    # provider internals defensively.
    previous_processors: list[Any] | None = None
    trace_processor_added = False
    provider = get_trace_provider()
    multi_processor = getattr(provider, "_multi_processor", None)
    current_processors = getattr(multi_processor, "_processors", None)
    if isinstance(current_processors, tuple):
        previous_processors = list(current_processors)

    try:
        # Step 4: Mark as patched and attach Datadog Pin/integration objects.
        # These attributes are dynamically added by ddtrace instrumentation.
        setattr(agents, "_datadog_patch", True)
        Pin().onto(agents)

        integration = OpenAIAgentsIntegration(integration_config=config.openai_agents)
        setattr(agents, "_datadog_integration", integration)

        # Step 5: Wrap the module-level turn entry points used by 0.8.3+.
        # Datadog's built-in patch currently wraps removed private methods.
        wrap(
            agents.run,
            "run_single_turn",
            _openai_agents_wrapper(agent_index=_RUN_SINGLE_TURN_AGENT_INDEX)(agents),
        )
        wrap(
            agents.run,
            "start_streaming",
            _openai_agents_wrapper(agent_index=_START_STREAMING_AGENT_INDEX)(agents),
        )

        # Step 6: Register Datadog processor only after wrap succeeded.
        # This avoids leaving a processor behind if wrapping raises.
        add_trace_processor(LLMObsTraceProcessor(integration))
        trace_processor_added = True
        return True
    except Exception:
        # Step 7: Best-effort rollback for partial patch states.
        if trace_processor_added:
            try:
                if previous_processors is not None:
                    set_trace_processors(previous_processors)
                else:
                    set_trace_processors([])
            except Exception:
                logger.debug(
                    "Failed to restore trace processors after patch error",
                    exc_info=True,
                )

        setattr(agents, "_datadog_patch", False)
        if hasattr(agents, "_datadog_integration"):
            delattr(agents, "_datadog_integration")
        try:
            pin = Pin.get_from(agents)
            if pin:
                pin.remove_from(agents)
        except Exception:
            logger.debug(
                "Failed to remove Datadog pin after patch error", exc_info=True
            )
        logger.info(
            "Skipping ddtrace LLM integration patch",
            extra={"integration": "openai_agents"},
            exc_info=True,
        )
        return False


def safe_enable_llmobs(ml_app: str = "pal", agentless_enabled: bool = True) -> bool:
    """
    Enable LLMObs safely without letting integration patch errors fail requests.

    Returns:
        bool: True when LLMObs is enabled for the current process.
    """
    global _llmobs_enabled, _llmobs_initialized

    if is_testing_mode():
        # Testing requests should never emit LLMObs data.
        try:
            LLMObs.disable()
        except Exception:
            logger.debug("Failed to disable LLMObs in testing mode", exc_info=True)
        return False

    if _llmobs_initialized:
        return _llmobs_enabled

    with _llmobs_lock:
        if _llmobs_initialized:
            return _llmobs_enabled

        try:
            # Disable ddtrace automatic integration patching.
            # We patch integrations manually so openai_agents uses our compatibility
            # path instead of ddtrace's default patch that targets removed methods.
            LLMObs.enable(
                ml_app=ml_app,
                agentless_enabled=agentless_enabled,
                integrations_enabled=False,
            )
            desired_integrations = [
                "anthropic",
                "google_genai",
                "openai",
                "openai_agents",
            ]
            patched_integrations: list[str] = []

            # Patch each integration independently so one provider failure doesn't
            # disable all LLM observability or fail message handling.
            for integration in desired_integrations:
                try:
                    if integration == "openai_agents":
                        if _patch_openai_agents_integration():
                            patched_integrations.append(integration)
                        continue

                    patch(raise_errors=True, **{integration: True})
                    patched_integrations.append(integration)
                except Exception:
                    logger.info(
                        "Skipping ddtrace LLM integration patch",
                        extra={"integration": integration},
                        exc_info=True,
                    )

            if not patched_integrations:
                logger.warning(
                    "LLMObs enabled but no LLM integrations could be patched",
                    extra={"integrations": desired_integrations},
                )
            elif (
                "openai_agents" in desired_integrations
                and "openai_agents" not in patched_integrations
            ):
                logger.warning(
                    "openai_agents integration is not patched; agent workflow traces will be missing",
                    extra={
                        "desired_integrations": desired_integrations,
                        "patched_integrations": patched_integrations,
                    },
                )
            _llmobs_enabled = True
        except Exception:
            _llmobs_enabled = False
            logger.warning(
                "Failed to initialize LLMObs safely; continuing without LLMObs integrations",
                exc_info=True,
            )
        finally:
            _llmobs_initialized = True

    return _llmobs_enabled


def traced(name, tags=None):
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)

        def _apply_tags(span):
            if tags:
                if not isinstance(tags, dict):
                    raise TypeError("tags must be a dictionary")
                for key, value in tags.items():
                    span.set_tag(key, value)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Skip tracing for testing requests
            if is_testing_mode():
                return await func(*args, **kwargs)
            with tracer.trace(name) as span:
                _apply_tags(span)
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Skip tracing for testing requests
            if is_testing_mode():
                return func(*args, **kwargs)
            with tracer.trace(name) as span:
                _apply_tags(span)
                return func(*args, **kwargs)

        return async_wrapper if is_async else sync_wrapper

    return decorator


def _setup_span(span, tags: Optional[Dict[str, Any]] = None):
    """Common setup code for spans"""
    if tags:
        if not isinstance(tags, dict):
            raise TypeError("tags must be a dictionary")
        for key, value in tags.items():
            span.set_tag(key, value)
    return span


def _handle_exception(span, e: Exception):
    """Common exception handling for spans"""
    span.set_tag("error", True)
    span.set_tag("error.msg", str(e))
    span.set_tag("error.type", e.__class__.__name__)  # Fix: was e.class.name
    raise


@contextmanager
def trace_block(name, resource=None, service=None, tags=None):
    """Synchronous trace block context manager"""
    # Skip tracing for testing requests
    if is_testing_mode():
        yield None
        return
    with tracer.trace(name, resource=resource, service=service) as span:
        _setup_span(span, tags)
        try:
            yield span
        except Exception as e:
            _handle_exception(span, e)


@asynccontextmanager
async def trace_async_block(name, resource=None, service=None, tags=None):
    """Asynchronous trace block context manager"""
    # Skip tracing for testing requests
    if is_testing_mode():
        yield None
        return
    with tracer.trace(name, resource=resource, service=service) as span:
        _setup_span(span, tags)
        try:
            yield span
        except Exception as e:
            _handle_exception(span, e)


# Initialize global DogStatsd client
# Use environment variables with defaults for configuration
statsd = DogStatsd(
    host=os.environ.get("DD_AGENT_HOST", "localhost"),
    port=int(os.environ.get("DD_AGENT_PORT", 8125)),
    namespace=os.environ.get("DD_NAMESPACE", None),
    constant_tags=[
        f"env:{os.environ.get('DD_ENV', 'dev')}",
        f"service:{os.environ.get('DD_SERVICE', 'pal-mono')}",
    ],
)


def dd_histogram_duration(name: str, duration_ms: float, tags: Optional[list] = None):
    # Skip metrics for testing requests
    if is_testing_mode():
        return
    env = os.getenv("RUNTIME_ENV", "none")
    base_tags = [f"env:{env}"]
    if tags:
        base_tags.extend(tags)
    statsd.histogram(name, duration_ms, tags=base_tags)


def send_dd_histogram_metrics(
    metrics_name: str, start_time: datetime.datetime, tags: Optional[list[str]] = None
):
    # Skip metrics for testing requests
    if is_testing_mode():
        return
    current_time = datetime.datetime.now(datetime.timezone.utc)
    duration_ms = (current_time - start_time).total_seconds() * 1000
    dd_histogram_duration(
        metrics_name,
        duration_ms,
        tags,
    )
