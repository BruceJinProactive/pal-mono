"""Tests for E14: Interruption evaluator."""

from services.eval_service.evaluators.interruption import evaluate_interruptions


def _entry(
    speaker: str,
    text: str,
    start: float = 0.0,
    end: float = 0.0,
) -> dict[str, object]:
    return {
        "speaker": speaker,
        "text": text,
        "start_time": start,
        "end_time": end,
    }


class TestEvaluateInterruptions:
    def test_empty_transcript(self) -> None:
        result = evaluate_interruptions([])
        assert result.score == 1.0
        assert result.passed is True
        assert result.metric_name == "interruption"

    def test_single_turn(self) -> None:
        result = evaluate_interruptions([_entry("agent", "Hello", 0.0, 1.0)])
        assert result.score == 1.0
        assert result.passed is True

    def test_clean_conversation(self) -> None:
        """No overlapping timestamps => all turns clean."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 1.5, 2.5),
            _entry("agent", "How can I help?", 3.0, 4.0),
            _entry("user", "I need a table", 4.5, 5.5),
        ]
        result = evaluate_interruptions(transcript)
        assert result.score == 1.0
        assert result.passed is True

    def test_overlap_detected(self) -> None:
        """User starts speaking before agent finishes => interrupted."""
        transcript = [
            _entry("agent", "Hello there, welcome to our restaurant", 0.0, 3.0),
            _entry("user", "Hi", 2.0, 2.5),  # starts at 2.0, agent ends at 3.0
            _entry("agent", "How can I help?", 3.0, 4.0),
        ]
        result = evaluate_interruptions(transcript)
        # 1 interrupted out of 3 => 2/3
        assert result.score == 2 / 3
        assert result.passed is False  # 0.667 < 0.8

    def test_same_speaker_overlap_ignored(self) -> None:
        """Overlapping timestamps from same speaker are not interruptions."""
        transcript = [
            _entry("agent", "Hello", 0.0, 2.0),
            _entry("agent", "Welcome", 1.5, 3.0),  # same speaker
        ]
        result = evaluate_interruptions(transcript)
        assert result.score == 1.0

    def test_tolerance_within_threshold(self) -> None:
        """Overlap within tolerance (50ms) is not counted."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 0.96, 1.5),  # 0.96 < 1.0 but within 50ms
        ]
        result = evaluate_interruptions(transcript)
        assert result.score == 1.0

    def test_tolerance_exceeded(self) -> None:
        """Overlap beyond tolerance is counted."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 0.90, 1.5),  # 0.90 < 1.0 - 0.05 = 0.95
        ]
        result = evaluate_interruptions(transcript)
        assert result.score == 0.5  # 1 interrupted out of 2

    def test_explicit_interruption_events(self) -> None:
        """Explicit interruption events mark turns as interrupted."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 1.5, 2.5),
            _entry("agent", "How can I help?", 3.0, 4.0),
        ]
        events = [{"turn_index": 1, "timestamp": 1.5, "source": "stt"}]
        result = evaluate_interruptions(transcript, interruption_events=events)
        assert result.score == 2 / 3
        assert "1" in result.reason  # turn index 1

    def test_explicit_event_out_of_range_ignored(self) -> None:
        """Events with turn_index beyond transcript length are ignored."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 1.5, 2.5),
        ]
        events = [{"turn_index": 99}]
        result = evaluate_interruptions(transcript, interruption_events=events)
        assert result.score == 1.0

    def test_both_signals_deduplicated(self) -> None:
        """Same turn flagged by both overlap and event counts once."""
        transcript = [
            _entry("agent", "Hello", 0.0, 3.0),
            _entry("user", "Hi", 2.0, 2.5),  # overlap
        ]
        events = [{"turn_index": 0}]  # same turn
        result = evaluate_interruptions(transcript, interruption_events=events)
        # turn 0 interrupted (both overlap at index 0 and event at index 0)
        assert result.score == 0.5

    def test_multiple_interruptions(self) -> None:
        """Multiple interruptions across a conversation."""
        transcript = [
            _entry("agent", "Hello", 0.0, 2.0),
            _entry("user", "Hi", 1.0, 1.5),  # overlap
            _entry("agent", "Welcome", 2.0, 4.0),
            _entry("user", "Thanks", 3.0, 3.5),  # overlap
            _entry("agent", "Sure", 4.0, 5.0),
        ]
        result = evaluate_interruptions(transcript)
        # 2 interrupted (index 0, 2), 5 total => 3/5 = 0.6
        assert result.score == 3 / 5
        assert result.passed is False

    def test_passing_threshold(self) -> None:
        """Score of exactly 0.8 passes."""
        transcript = [
            _entry("agent", "Hello", 0.0, 2.0),
            _entry("user", "Hi", 1.0, 1.5),  # overlap
            _entry("agent", "A", 2.0, 3.0),
            _entry("user", "B", 3.5, 4.0),
            _entry("agent", "C", 4.5, 5.0),
        ]
        result = evaluate_interruptions(transcript)
        # 1 interrupted out of 5 => 4/5 = 0.8
        assert result.score == 4 / 5
        assert result.passed is True

    def test_zero_timestamps_skipped(self) -> None:
        """Entries with zero timestamps don't trigger overlap detection."""
        transcript = [
            _entry("agent", "Hello", 0.0, 0.0),
            _entry("user", "Hi", 0.0, 0.0),
        ]
        result = evaluate_interruptions(transcript)
        assert result.score == 1.0
