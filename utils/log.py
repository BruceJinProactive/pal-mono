import logging
import os

from agno.utils.log import LOGGER_NAME
from pythonjsonlogger import jsonlogger

# Exclude watchdog DEBUG and INFO logs
logging.getLogger("watchdog").setLevel(logging.WARNING)

# Exclude httpx DEBUG and INFO logs
logging.getLogger("httpx").setLevel(logging.WARNING)


class DatadogJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that adds Datadog reserved attributes at top level."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        # Add Datadog reserved attributes as top-level fields for filtering
        # Only set if not already present
        if "env" not in log_record:
            log_record["env"] = os.getenv("DD_ENV") or os.getenv("RUNTIME_ENV", "dev")
        if "service" not in log_record:
            log_record["service"] = os.getenv("DD_SERVICE") or "pal-mono"


def configure_global_logger():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove any default handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = DatadogJsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def patch_agno_logger_to_use_root():
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = True


# Usage
logger = logging.getLogger("pal-mono")
