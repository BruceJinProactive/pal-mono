import asyncio
import os
import threading
from utils.log import logger


async def log_sys_info(desc: str):
    """Log system information in a single log entry."""
    log_message = (
        f"{desc}\n"
        f"Process ID: {os.getpid()}\n"
        f"Thread name: {threading.current_thread().name}\n"
        f"Thread ID: {threading.get_ident()}\n"
        f"Event loop: {asyncio.get_running_loop()}\n"
        f"Current task: {asyncio.current_task()}"
    )
    logger.debug(log_message)
