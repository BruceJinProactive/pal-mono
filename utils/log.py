import logging
import os
from contextvars import ContextVar

from agno.utils.log import LOGGER_NAME
from opentelemetry import trace
from pythonjsonlogger import jsonlogger

# Exclude noisy library logs (these produce ~2.2M logs/4h at INFO level)
# AWS SDK internals: event handlers, auth signing, endpoint resolution, retry logic
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
# S3 transfer internals: IOWriteTask, multipart upload progress
logging.getLogger("s3transfer").setLevel(logging.WARNING)
# Datadog tracing internals: span finishing, trace completion, sampler init
logging.getLogger("ddtrace").setLevel(logging.WARNING)
# OpenTelemetry SDK internals: exporter lifecycle, batch processor
logging.getLogger("opentelemetry").setLevel(logging.WARNING)
# HTTP connection pool noise: acquire/release
logging.getLogger("urllib3").setLevel(logging.WARNING)
# File watcher and HTTP client
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
# Agno agent framework internals: message role separators, debug traces
logging.getLogger("agno").setLevel(logging.WARNING)
# Multipart form parser internals: header field/value parsing callbacks
logging.getLogger("python_multipart.multipart").setLevel(logging.WARNING)
# OpenAI SDK internals: logs full HTTP request/response payloads including base64 image data
logging.getLogger("openai").setLevel(logging.WARNING)
# HTTP core connection internals: connection lifecycle, data sent/received
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Context variable for request correlation ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class OTelJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that adds OTel trace correlation and service attributes."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        # Add service attributes as top-level fields for filtering
        if "env" not in log_record:
            log_record["env"] = os.getenv("DD_ENV") or os.getenv("RUNTIME_ENV", "dev")
        if "service" not in log_record:
            log_record["service"] = (
                os.getenv("OTEL_SERVICE_NAME") or os.getenv("DD_SERVICE") or "pal-mono"
            )

        # Inject OTel trace correlation IDs for log-trace linking
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"] = format(ctx.span_id, "016x")
            # Backward compat: DD log pipelines expect dd.* fields during transition
            log_record["dd.trace_id"] = str(ctx.trace_id)
            log_record["dd.span_id"] = str(ctx.span_id)

        # Inject request correlation ID if available
        rid = request_id_ctx.get()
        if rid:
            log_record["request_id"] = rid


def configure_global_logger():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove any default handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = OTelJsonFormatter(fmt="%(asctime)s %(name)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def patch_agno_logger_to_use_root():
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = True


# Usage
logger = logging.getLogger("pal-mono")
