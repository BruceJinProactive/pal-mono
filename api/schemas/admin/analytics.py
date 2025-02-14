from enum import Enum


class Event(str, Enum):
    """Anslytics Event"""

    AGENT_MESSAGE = "Agent Message"
    USER_MESSAGE = "User Message"
