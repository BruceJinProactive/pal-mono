"""Tests for _should_track_call_usage billing skip rules."""

from unittest.mock import patch

from api.routes.internal._voice import _should_track_call_usage


class TestShouldTrackCallUsage:
    """Unit tests for _should_track_call_usage filtering rules."""

    def _conversation_with_user_turn(self) -> list[dict]:
        return [
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Hi, I'd like to order."},
        ]

    def test_eval_call_skipped(self) -> None:
        """Eval calls are never billed regardless of other conditions."""
        should_track, reason = _should_track_call_usage(
            caller_number="+15551234567",
            duration_seconds=60.0,
            conversation_history=self._conversation_with_user_turn(),
            is_eval=True,
        )
        assert should_track is False
        assert reason == "eval_call"

    def test_normal_call_tracked(self) -> None:
        """Normal calls meeting all criteria are tracked."""
        should_track, reason = _should_track_call_usage(
            caller_number="+15551234567",
            duration_seconds=60.0,
            conversation_history=self._conversation_with_user_turn(),
            is_eval=False,
        )
        assert should_track is True
        assert reason == ""

    def test_short_call_skipped(self) -> None:
        """Calls under 10 seconds are not tracked."""
        should_track, reason = _should_track_call_usage(
            caller_number="+15551234567",
            duration_seconds=5.0,
            conversation_history=self._conversation_with_user_turn(),
            is_eval=False,
        )
        assert should_track is False
        assert "call_too_short" in reason

    @patch("api.routes.internal._voice._is_test_phone_number", return_value=True)
    @patch.dict("os.environ", {"RUNTIME_ENV": "prd"})
    def test_test_number_skipped_in_production(self, mock_is_test: object) -> None:
        """Test phone numbers are skipped in production."""
        should_track, reason = _should_track_call_usage(
            caller_number="+18889738742",
            duration_seconds=60.0,
            conversation_history=self._conversation_with_user_turn(),
            is_eval=False,
        )
        assert should_track is False
        assert "test_number" in reason

    def test_is_eval_defaults_false(self) -> None:
        """is_eval defaults to False for backwards compatibility."""
        should_track, reason = _should_track_call_usage(
            caller_number="+15551234567",
            duration_seconds=60.0,
            conversation_history=self._conversation_with_user_turn(),
        )
        assert should_track is True
