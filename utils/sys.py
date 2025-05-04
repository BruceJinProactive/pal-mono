import asyncio
import os
import threading

from utils.log import logger


def log_sys_info(desc: str):
    """Log system information in a single log entry."""
    log_message = (
        f"[System Info]{desc}\n"
        f"Process ID: {os.getpid()}\n"
        f"Thread name: {threading.current_thread().name}\n"
        f"Thread ID: {threading.get_ident()}\n"
        f"Event loop: {_get_event_loop_info()}\n"
        f"Current task: {asyncio.current_task() or 'No current task'}"
    )
    logger.debug(log_message)


def _get_event_loop_info():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return "Not in event loop"
