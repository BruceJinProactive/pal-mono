from unittest.mock import MagicMock

import pytest
import streamlit as st
from sqlalchemy.orm import Session

from app.shared import json_decode, set_account


def test_set_account(mocker):
    mock_session = MagicMock(spec=Session)
    mock_project = MagicMock()
    mock_project.name = "TestProject"
    mock_account = MagicMock()
    mock_account.projects = [mock_project]
    mocker.patch(
        "app.shared.get_account",
        return_value=mock_account,
    )
    set_account(mock_session, "TestAccount")
    assert st.session_state["account_name"] == "TestAccount"
    assert st.session_state["project_name"] == "TestProject"


def test_set_account_invalid(mocker):
    """
    Tests set_account with a nonexistent account name
    """
    mock_session = MagicMock(spec=Session)
    mocker.patch(
        "app.shared.get_account",
        return_value=None,
    )
    with pytest.raises(ValueError):
        set_account(mock_session, "InvalidAccount")


def test_json_decode():
    assert json_decode('{"key": "value"}') == {"key": "value"}


def test_json_decode_invalid():
    assert json_decode("invalid json") == {}
