import logging
import os

from agno.utils.log import LOGGER_NAME
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


def patch_agno_logger_to_use_root():
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = True


# Usage
logger = logging.getLogger("pal-mono")
