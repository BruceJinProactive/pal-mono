import logging
import os

from pythonjsonlogger import jsonlogger
from rich.logging import RichHandler

# Exclude watchdog DEBUG and INFO logs
logging.getLogger("watchdog").setLevel(logging.WARNING)


def build_logger(logger_name: str) -> logging.Logger:
    # Get log level from environment variable, defaulting to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # JSON formatter for structured logs
    json_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    rich_handler = RichHandler(
        show_time=False, rich_tracebacks=False, tracebacks_show_locals=False
    )
    rich_handler.setFormatter(json_formatter)  # Use JSON formatter for console output

    _logger = logging.getLogger(logger_name)
    _logger.addHandler(rich_handler)
    _logger.setLevel(getattr(logging, log_level, logging.INFO))
    _logger.propagate = False
    return _logger


logger = build_logger("pal-mono")
