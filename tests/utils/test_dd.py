from unittest.mock import patch

import pytest

from utils.dd import safe_annotate


class TestSafeAnnotate:
    """Tests for safe_annotate wrapper around LLMObs.annotate."""

    @patch("utils.dd.is_testing_mode", return_value=True)
    def test_skips_in_testing_mode(self, mock_testing_mode):
        """safe_annotate should return early when testing mode is enabled."""
        with patch("utils.dd.LLMObs.annotate") as mock_annotate:
            safe_annotate(tags={"test": True})
            mock_annotate.assert_not_called()

    @patch("utils.dd.is_testing_mode", return_value=False)
    @patch("utils.dd.LLMObs.annotate")
    def test_calls_llmobs_annotate(self, mock_annotate, mock_testing_mode):
        """safe_annotate should forward kwargs to LLMObs.annotate."""
        safe_annotate(tags={"key": "value"}, input_data="test")
        mock_annotate.assert_called_once_with(tags={"key": "value"}, input_data="test")

    @patch("utils.dd.is_testing_mode", return_value=False)
    @patch("utils.dd.LLMObs.annotate")
    def test_suppresses_no_span_error(self, mock_annotate, mock_testing_mode):
        """safe_annotate should catch and suppress the 'no span' error."""
        mock_annotate.side_effect = Exception(
            "No span provided and no active LLMObs-generated span found. "
            "Ensure you pass the span explicitly using LLMObs.annotate(span=<your_span>, ...) "
            "when annotating from a different thread or async task than where the span was created."
        )
        # Should NOT raise
        safe_annotate(tags={"test": True})

    @patch("utils.dd.is_testing_mode", return_value=False)
    @patch("utils.dd.LLMObs.annotate")
    def test_reraises_other_exceptions(self, mock_annotate, mock_testing_mode):
        """safe_annotate should re-raise exceptions that are not the 'no span' error."""
        mock_annotate.side_effect = ValueError("unexpected error")
        with pytest.raises(ValueError, match="unexpected error"):
            safe_annotate(tags={"test": True})

    @patch("utils.dd.is_testing_mode", return_value=False)
    @patch("utils.dd.LLMObs.annotate")
    def test_logs_debug_on_no_span_error(self, mock_annotate, mock_testing_mode):
        """safe_annotate should log a debug message when suppressing the 'no span' error."""
        mock_annotate.side_effect = Exception(
            "No span provided and no active LLMObs-generated span found."
        )
        with patch("utils.dd.logger") as mock_logger:
            safe_annotate(tags={"test": True})
            mock_logger.debug.assert_called_once_with(
                "LLMObs.annotate() skipped: no active span in current context"
            )
