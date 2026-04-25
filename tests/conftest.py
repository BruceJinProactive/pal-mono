from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_langfuse_client():
    """Auto-mock Langfuse client to prevent real API calls during tests."""
    mock_client = MagicMock()
    with patch("langfuse.get_client", return_value=mock_client):
        yield mock_client
