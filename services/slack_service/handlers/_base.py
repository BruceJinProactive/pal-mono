"""
Base Message Handler Interface

Defines the abstract interface that all message handlers must implement.
"""

from abc import ABC, abstractmethod


class MessageHandler(ABC):
    """
    Base class for all Slack message handlers.

    Handlers are responsible for:
    1. Identifying if they can handle a message (pattern matching)
    2. Processing the message and generating appropriate responses
    """

    @abstractmethod
    def get_patterns(self) -> list[str]:
        """
        Return list of regex patterns this handler can process.

        Returns:
            list[str]: List of regex pattern strings
        """
        pass

    @abstractmethod
    async def handle(self, message, client):
        """
        Process a message and send appropriate response.

        Args:
            message: Slack message event object
            client: Slack AsyncWebClient for API calls
        """
        pass
