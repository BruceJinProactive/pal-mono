from datetime import datetime, timedelta, timezone

import pytest

from db.repositories.conversation_repository import ConversationRepository
from db.repositories.user_repository import UserRepository

from . import _implementation

get_conversation_messages = _implementation.get_conversation_messages
_include_conversation_preview = _implementation._include_conversation_preview


def test_include_conversation_preview_no_message(mocker):
    """
    Test _include_conversation_preview without a message

    Expected result: reject
    """
    assert not _include_conversation_preview(None, 5)


def test_include_conversation_preview_no_limit(mocker):
    """
    Test _include_conversation_preview without a limit

    Expected result: accept
    """
    assert _include_conversation_preview(mocker.Mock(), 0)


def test_include_conversation_preview_within_limit(mocker):
    """
    Test _include_conversation_preview with a message with a creation time within the specified limit

    Expected result: accept
    """
    message_mock = mocker.Mock()
    message_mock.created_at = datetime.now(timezone.utc) - timedelta(minutes=4.9)
    assert _include_conversation_preview(message_mock, 5)


def test_include_conversation_preview_outside_limit(mocker):
    """
    Test _include_conversation_preview with a message with a creation time outside the specified limit

    Expected result: reject
    """
    message_mock = mocker.Mock()
    message_mock.created_at = datetime.now(timezone.utc) - timedelta(minutes=5.1)
    assert not _include_conversation_preview(message_mock, 5)


def test_get_conversation_messages_valid_user(mocker):
    """
    Test get_conversation_messages with a properly authorized user

    Expected result: desired messages are fetched
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

    Expected result: return error
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
