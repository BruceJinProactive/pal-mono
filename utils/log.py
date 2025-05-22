import logging
import os

from pythonjsonlogger import jsonlogger

# Exclude watchdog DEBUG and INFO logs
logging.getLogger("watchdog").setLevel(logging.WARNING)


def configure_global_logger():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove any default handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


# Usage
logger = logging.getLogger("pal-mono")
