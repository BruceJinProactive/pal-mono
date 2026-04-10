import asyncio
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import Any, AsyncIterator, Dict, Iterator, Optional

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from utils.dd import is_testing_mode

_tracer = trace.get_tracer(__name__)


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
