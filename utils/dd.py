import asyncio
from functools import wraps

from ddtrace import tracer  # pyright: ignore[reportPrivateImportUsage]


def traced(name, tags=None):
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)

        def _apply_tags(span):
            if tags is not None:
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
