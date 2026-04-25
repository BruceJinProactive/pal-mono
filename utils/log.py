import logging
import os
from contextvars import ContextVar

from agno.utils.log import LOGGER_NAME
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from pythonjsonlogger import jsonlogger

# Exclude noisy library logs (these produce ~2.2M logs/4h at INFO level)
# AWS SDK internals: event handlers, auth signing, endpoint resolution, retry logic
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
# S3 transfer internals: IOWriteTask, multipart upload progress
logging.getLogger("s3transfer").setLevel(logging.WARNING)
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
            log_record["env"] = os.getenv("RUNTIME_ENV", "dev")
        if "service" not in log_record:
            log_record["service"] = os.getenv("OTEL_SERVICE_NAME", "pal-mono")

        # LoggingInstrumentor auto-injects otelTraceID/otelSpanID on each LogRecord.
        # Map them to our standard field names for log-trace linking.
        otel_trace_id = getattr(record, "otelTraceID", "0")
        otel_span_id = getattr(record, "otelSpanID", "0")
        if otel_trace_id != "0":
            log_record["trace_id"] = otel_trace_id
            log_record["span_id"] = otel_span_id

        # Inject request correlation ID if available
        rid = request_id_ctx.get()
        if rid:
            log_record["request_id"] = rid


def configure_global_logger():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove non-OTel handlers to avoid duplicates, but preserve LoggingHandler
    # which bridges Python logging → OTel SDK → OTLP export (set up by
    # `opentelemetry-instrument` bootstrap when OTEL_LOGS_EXPORTER=otlp).
    for h in root_logger.handlers[:]:
        if not isinstance(h, LoggingHandler):
            root_logger.removeHandler(h)

    handler = logging.StreamHandler()
    formatter = OTelJsonFormatter(fmt="%(asctime)s %(name)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Activate OTel logging instrumentation — auto-injects trace/span IDs
    # into every LogRecord (otelTraceID, otelSpanID, otelTraceSampled, etc.)
    # Guard against repeated calls — instrument() is not idempotent.
    instrumentor = LoggingInstrumentor()
    if not instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.instrument()


def patch_agno_logger_to_use_root():
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = True


# Usage
logger = logging.getLogger("pal-mono")
