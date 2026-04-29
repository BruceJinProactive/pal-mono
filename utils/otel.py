import asyncio
import datetime
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, AsyncIterator, Dict, Iterator, Optional

from opentelemetry import metrics, trace
from opentelemetry.trace import StatusCode

# ---------------------------------------------------------------------------
# Testing-mode context variable (moved from utils/dd)
# When True, all OTel tracing and metrics are suppressed for the request.
# ---------------------------------------------------------------------------
_testing_mode: ContextVar[bool] = ContextVar("testing_mode", default=False)


def set_testing_mode(testing: bool) -> None:
    """Set testing mode for current request context."""
    _testing_mode.set(testing)


def is_testing_mode() -> bool:
    """Check if current request is in testing mode."""
    return _testing_mode.get()


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------
_tracer = trace.get_tracer(__name__)

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
_meter = metrics.get_meter(
    "pal-mono",
    schema_url="https://opentelemetry.io/schemas/1.21.0",
)

_counters: Dict[str, metrics.Counter] = {}
_histograms: Dict[str, metrics.Histogram] = {}


def _get_counter(name: str) -> metrics.Counter:
    if name not in _counters:
        _counters[name] = _meter.create_counter(name)
    return _counters[name]


def _get_histogram(name: str, unit: str = "") -> metrics.Histogram:
    if name not in _histograms:
        _histograms[name] = _meter.create_histogram(name, unit=unit)
    return _histograms[name]


def increment_counter(name: str, attributes: Optional[Dict[str, str]] = None) -> None:
    """Increment an OTel counter by 1. No-op in testing mode."""
    if is_testing_mode():
        return
    _get_counter(name).add(1, attributes=attributes)


def record_histogram(
    name: str,
    value: float,
    attributes: Optional[Dict[str, str]] = None,
    unit: str = "",
) -> None:
    """Record a value on an OTel histogram. No-op in testing mode."""
    if is_testing_mode():
        return
    _get_histogram(name, unit=unit).record(value, attributes=attributes)


def record_duration(
    name: str,
    start_time: datetime.datetime,
    attributes: Optional[Dict[str, str]] = None,
) -> None:
    """Compute elapsed ms from *start_time* and record on a histogram.

    Drop-in replacement for the old ``send_dd_histogram_metrics``.
    """
    if is_testing_mode():
        return
    current_time = datetime.datetime.now(datetime.timezone.utc)
    duration_ms = (current_time - start_time).total_seconds() * 1000
    _get_histogram(name, unit="ms").record(duration_ms, attributes=attributes)


def traced(name: str, tags: Optional[Dict[str, Any]] = None):
    """Decorator that wraps a sync or async function in an OTel span."""

    def decorator(func):  # type: ignore[no-untyped-def]
        is_async = asyncio.iscoroutinefunction(func)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if is_testing_mode():
                return await func(*args, **kwargs)
            with _tracer.start_as_current_span(name) as span:
                _apply_tags(span, tags)
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    _handle_exception(span, e)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if is_testing_mode():
                return func(*args, **kwargs)
            with _tracer.start_as_current_span(name) as span:
                _apply_tags(span, tags)
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    _handle_exception(span, e)

        return async_wrapper if is_async else sync_wrapper

    return decorator


def _apply_tags(span: trace.Span, tags: Optional[Dict[str, Any]] = None) -> None:
    """Set span attributes from a tags dictionary."""
    if tags:
        if not isinstance(tags, dict):
            raise TypeError("tags must be a dictionary")
        for key, value in tags.items():
            span.set_attribute(key, value)


def _handle_exception(span: trace.Span, e: Exception) -> None:
    """Record exception on span and re-raise."""
    span.set_status(StatusCode.ERROR, str(e))
    span.record_exception(e)
    raise e


@contextmanager
def trace_block(
    name: str,
    resource: Optional[str] = None,
    service: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None,
) -> Iterator[Optional[trace.Span]]:
    """Synchronous trace block context manager."""
    if is_testing_mode():
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if resource:
            span.set_attribute("resource.name", resource)
        if service:
            span.set_attribute("service.name", service)
        _apply_tags(span, tags)
        try:
            yield span
        except Exception as e:
            _handle_exception(span, e)


@asynccontextmanager
async def trace_async_block(
    name: str,
    resource: Optional[str] = None,
    service: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Optional[trace.Span]]:
    """Asynchronous trace block context manager."""
    if is_testing_mode():
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if resource:
            span.set_attribute("resource.name", resource)
        if service:
            span.set_attribute("service.name", service)
        _apply_tags(span, tags)
        try:
            yield span
        except Exception as e:
            _handle_exception(span, e)
