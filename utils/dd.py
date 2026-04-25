import datetime
import os
from contextvars import ContextVar
from typing import Optional

from datadog import DogStatsd  # pyright: ignore[reportPrivateImportUsage]

# Context variable to track testing mode for current request
# When True, all Datadog logging/tracing is disabled for the request
_testing_mode: ContextVar[bool] = ContextVar("testing_mode", default=False)


def set_testing_mode(testing: bool) -> None:
    """Set testing mode for current request context."""
    _testing_mode.set(testing)


def is_testing_mode() -> bool:
    """Check if current request is in testing mode."""
    return _testing_mode.get()


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


def dd_histogram_duration(
    name: str, duration_ms: float, tags: Optional[list] = None
) -> None:
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
) -> None:
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
