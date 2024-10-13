import logging
import os

from pythonjsonlogger import jsonlogger

# Exclude watchdog DEBUG and INFO logs
logging.getLogger("watchdog").setLevel(logging.WARNING)


def build_logger(logger_name: str) -> logging.Logger:
    # Get log level from environment variable, defaulting to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False

    # Create formatter
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    # Create handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Usage
logger = build_logger("pal-mono")
