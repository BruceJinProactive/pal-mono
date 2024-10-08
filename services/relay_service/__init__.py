from datetime import datetime

from api.schemas.message.message import Message
from utils.dttm import current_utc

from . import _implementation


def send_message(message: Message, delivery_time: datetime = current_utc()) -> dict:
    """
    Send a message with an optional delivery time.

    Args:
        message (Message): The message object to be sent.
        delivery_time (datetime, optional): The time at which the message should be delivered. Defaults to the current UTC time.

    Returns:
        dict: A dictionary containing the status of the message sending operation.
    """
    return _implementation.send_message(message, delivery_time)


__all__ = ["send_message"]
