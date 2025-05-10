import asyncio
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import Any, Dict, Optional

from ddtrace import tracer  # pyright: ignore[reportPrivateImportUsage]


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
            with tracer.trace(name) as span:
                _apply_tags(span)
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
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
    with tracer.trace(name, resource=resource, service=service) as span:
        _setup_span(span, tags)
        try:
            yield span
        except Exception as e:
            _handle_exception(span, e)


@asynccontextmanager
async def trace_async_block(name, resource=None, service=None, tags=None):
    with tracer.trace(name, resource=resource, service=service) as span:
        _setup_span(span, tags)
        try:
            yield span
        except Exception as e:
            _handle_exception(span, e)
