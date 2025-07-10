from datetime import datetime, timezone

from api.schemas.chat.message import Message

from . import _implementation


def send_message(
    message: Message, delivery_time: datetime = datetime.now(timezone.utc)
) -> dict:
    """
    Send a message with an optional delivery time.

    Args:
        message (Message): The message object to be sent.
        delivery_time (datetime, optional): The time at which the message should be delivered. Defaults to the current UTC time.

    Returns:
        dict: A dictionary containing the status of the message sending operation.
    """
    return _implementation.send_message(message, delivery_time)


def send_messages(
    messages: list[Message], delivery_time: datetime = datetime.now(timezone.utc)
) -> list[dict]:
    """
    Send multiple messages with an optional delivery time.

    Args:
        messages (list[Message]): A list of message objects to be sent.
        delivery_time (datetime, optional): The time at which the messages should be delivered. Defaults to the current UTC time.

    Returns:
        list[dict]: A list of dictionaries containing the statuses of the message sending operations.
    """
    return _implementation.send_messages(messages, delivery_time)


__all__ = ["send_message", "send_messages"]
