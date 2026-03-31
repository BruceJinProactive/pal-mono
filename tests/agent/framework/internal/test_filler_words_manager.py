"""Tests for FillerWordsManager."""

import pytest

from agent.framework.internal.filler_words_manager import FillerType, FillerWordsManager


@pytest.fixture
def manager() -> FillerWordsManager:
    """Create a FillerWordsManager instance for testing."""
    return FillerWordsManager(
        agent_id="test-agent-id",
        account_name="test-account",
    )


class TestGetFillerWords:
    """Tests for get_filler_words method."""

    def test_returns_filler_with_newline_for_english(self, manager: FillerWordsManager):
        """Test that a filler word is returned with a newline for English."""
        result = manager.get_filler_words(
            language="ENGLISH",
            filler_type=FillerType.CHAT,
            input_content="I want to order food",
        )

        # Should return a non-empty string with newline
        assert result != ""
        assert result.endswith("\n")
        assert len(result) > 1  # More than just the newline

    def test_returns_filler_with_newline_for_spanish(self, manager: FillerWordsManager):
        """Test that a filler word is returned with a newline for Spanish."""
        result = manager.get_filler_words(
            language="SPANISH",
            filler_type=FillerType.TOOL_CALLING,
            input_content="Quiero hacer una reserva",
        )

        # Should return a non-empty string with newline
        assert result != ""
        assert result.endswith("\n")
        assert len(result) > 1

    def test_returns_filler_with_newline_for_chinese(self, manager: FillerWordsManager):
        """Test that a filler word is returned with a newline for Chinese."""
        result = manager.get_filler_words(
            language="CHINESE",
            filler_type=FillerType.CHAT,
            input_content="我想点菜",
        )

        # Should return a non-empty string with newline
        assert result != ""
        assert result.endswith("\n")
        assert len(result) > 1

    def test_returns_empty_for_unsupported_language(self, manager: FillerWordsManager):
        """Test that empty string is returned for unsupported language."""
        result = manager.get_filler_words(
            language="KLINGON",
            filler_type=FillerType.CHAT,
            input_content="test",
        )

        assert result == ""

    def test_fallback_filler_with_newline(self, manager: FillerWordsManager):
        """Test that fallback fillers also return with newline."""
        # Generic input that should trigger fallback
        result = manager.get_filler_words(
            language="ENGLISH",
            filler_type=FillerType.CHAT,
            input_content="hello",
        )

        # Should return a filler with newline (fallback path)
        assert result != ""
        assert result.endswith("\n")
