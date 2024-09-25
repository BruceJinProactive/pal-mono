import os

import pytest

from db.repositories.conversation_repository import ConversationRepository
from db.repositories.user_repository import UserRepository

if os.getenv("ci"):
    from . import get_conversation_messages
else:
    from . import _implementation

    get_conversation_messages = _implementation.get_conversation_messages


def test_get_conversation_messages_valid_user(mocker):
    """
    Test get_conversation_messages with a properly authorized user

    This is expected fetch the desired messages
    """
    conversation_mock = mocker.Mock()
    conversation_mock.user_id = 2
    user_mock = mocker.Mock()
    user_mock.account_id = 0
    messages = ["mock_message1", "mock_message2"]

    mocker.patch.object(
        ConversationRepository, "get_conversation_by_id", return_value=conversation_mock
    )
    mocker.patch.object(UserRepository, "get_user_by_id", return_value=user_mock)
    mocker.patch(
        "services.admin_service._implementation.get_messages_by_conversation",
        return_value=messages,
    )
    assert get_conversation_messages(None, 0, 0) == messages


def test_get_conversation_messages_invalid_auth(mocker):
    """
    Test get_conversation_messages with a user that should not have access to those conversations

    This is expected to return an error
    """
    conversation_mock = mocker.Mock()
    conversation_mock.user_id = 0
    user_mock = mocker.Mock()
    user_mock.account_id = 1

    mocker.patch.object(
        ConversationRepository, "get_conversation_by_id", return_value=conversation_mock
    )
    mocker.patch.object(UserRepository, "get_user_by_id", return_value=user_mock)
    with pytest.raises(ValueError):
        get_conversation_messages(None, 0, 0)
