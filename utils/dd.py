import asyncio
import datetime
import os
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Dict, Optional

from datadog import DogStatsd  # pyright: ignore[reportPrivateImportUsage]
from ddtrace import tracer  # pyright: ignore[reportPrivateImportUsage]
from ddtrace.llmobs import LLMObs

from utils.log import logger

# Context variable to track testing mode for current request
# When True, all Datadog logging/tracing is disabled for the request
_testing_mode: ContextVar[bool] = ContextVar("testing_mode", default=False)


def set_testing_mode(testing: bool) -> None:
    """Set testing mode for current request context."""
    _testing_mode.set(testing)


def is_testing_mode() -> bool:
    """Check if current request is in testing mode."""
    return _testing_mode.get()


def safe_annotate(**kwargs: Any) -> None:
    """Safely call LLMObs.annotate, suppressing errors when no active span exists.

    Some code paths run in detached threads or background async tasks where the
    parent LLMObs span context is not available. In those cases LLMObs.annotate()
    raises an error. This wrapper catches that specific case and logs a debug
    message instead of propagating the exception.

    All keyword arguments are forwarded directly to LLMObs.annotate().
    """
    if is_testing_mode():
        return
    try:
        LLMObs.annotate(**kwargs)
    except Exception as e:
        if "No span provided and no active LLMObs-generated span found" in str(e):
            logger.debug("LLMObs.annotate() skipped: no active span in current context")
        else:
            raise


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
