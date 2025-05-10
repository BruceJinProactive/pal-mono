import asyncio
from contextlib import contextmanager
from functools import wraps

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


@contextmanager
def trace_block(name, resource=None, service=None, tags=None):
    with tracer.trace(
        name,
        resource=resource,
        service=service,
    ) as span:
        if tags:
            if not isinstance(tags, dict):
                raise TypeError("tags must be a dictionary")

            for key, value in tags.items():
                span.set_tag(key, value)

        try:
            yield span
        except Exception as e:
            span.set_tag("error", True)
            span.set_tag("error.msg", str(e))
            span.set_tag("error.type", e.__class__.__name__)
            raise
