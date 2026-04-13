"""Tests for E15: Latency and silence evaluator."""

from services.eval_service.evaluators.latency_silence import evaluate_latency_silence


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


class TestEvaluateLatencySilence:
    # --- Edge cases ---

    def test_no_data(self) -> None:
        result = evaluate_latency_silence([], None)
        assert result.score == 1.0
        assert result.passed is True
        assert result.metric_name == "latency_silence"

    def test_empty_latencies_empty_transcript(self) -> None:
        result = evaluate_latency_silence([], [])
        assert result.score == 1.0

    # --- Latency-only tests ---

    def test_latency_within_sla(self) -> None:
        """All turns well under SLA => score ~1.0."""
        latencies = [500.0, 600.0, 700.0, 800.0]
        result = evaluate_latency_silence(latencies)
        assert result.score == 1.0
        assert result.passed is True
        assert result.raw_output is not None
        assert result.raw_output["p50_ms"] <= 1500
        assert result.raw_output["p95_ms"] <= 3000

    def test_latency_at_sla_boundary(self) -> None:
        """p50 exactly at SLA threshold => p50_score = 1.0."""
        latencies = [1500.0] * 10
        result = evaluate_latency_silence(latencies)
        assert result.raw_output is not None
        assert result.raw_output["p50_score"] == 1.0

    def test_latency_exceeds_sla(self) -> None:
        """All turns double the SLA => score = 0."""
        latencies = [3000.0] * 10  # p50=3000, p95=3000
        result = evaluate_latency_silence(latencies)
        assert result.raw_output is not None
        # p50: (3000-1500)/1500 = 1.0 => p50_score=0.0
        # p95: (3000-3000)/3000 = 0.0 => p95_score=1.0
        assert result.raw_output["p50_score"] == 0.0
        assert result.raw_output["p95_score"] == 1.0
        # Composite = 0.5 * 0 + 0.5 * 1 = 0.5
        assert result.score == 0.5

    def test_latency_degraded_p95(self) -> None:
        """Most turns fast but some slow => p95 penalized."""
        latencies = [500.0] * 15 + [5000.0] * 5
        result = evaluate_latency_silence(latencies)
        assert result.raw_output is not None
        assert result.raw_output["p50_ms"] < 1500
        assert result.raw_output["p95_ms"] > 3000

    def test_single_turn_latency(self) -> None:
        """Single turn: p50=p95=that value."""
        result = evaluate_latency_silence([1000.0])
        assert result.raw_output is not None
        assert result.raw_output["p50_ms"] == 1000.0
        assert result.raw_output["p95_ms"] == 1000.0

    # --- Silence-only tests ---

    def test_no_silence_gaps(self) -> None:
        """Tight transitions => silence score = 1.0."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 1.5, 2.5),
            _entry("agent", "How can I help?", 2.8, 4.0),
        ]
        result = evaluate_latency_silence([], transcript)
        assert result.score == 1.0
        assert result.passed is True

    def test_one_silence_gap(self) -> None:
        """One gap > 3s penalizes silence score."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "...", 5.0, 5.5),  # 4s gap
            _entry("agent", "Still there?", 6.0, 7.0),
        ]
        result = evaluate_latency_silence([], transcript)
        # 1 gap out of 2 transitions => silence_score = 1/2 = 0.5
        assert result.score == 0.5
        assert result.passed is False
        assert result.raw_output is not None
        assert result.raw_output["silence_gap_count"] == 1

    def test_multiple_silence_gaps(self) -> None:
        """Multiple gaps."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "...", 5.0, 5.5),  # 4s gap
            _entry("agent", "...", 9.0, 10.0),  # 3.5s gap
        ]
        result = evaluate_latency_silence([], transcript)
        # 2 gaps out of 2 transitions => silence_score = 0.0
        assert result.score == 0.0
        assert result.passed is False

    def test_gap_just_under_threshold(self) -> None:
        """2.9s gap does not count as awkward silence."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 3.9, 4.5),  # 2.9s gap < 3.0s
        ]
        result = evaluate_latency_silence([], transcript)
        assert result.score == 1.0

    def test_gap_exactly_at_threshold(self) -> None:
        """Exactly 3.0s gap counts."""
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 4.0, 4.5),  # 3.0s gap
        ]
        result = evaluate_latency_silence([], transcript)
        assert result.score == 0.0  # 1 gap out of 1 transition

    def test_zero_timestamps_ignored(self) -> None:
        """Entries with zero timestamps don't create false gaps."""
        transcript = [
            _entry("agent", "Hello", 0.0, 0.0),
            _entry("user", "Hi", 0.0, 0.0),
        ]
        result = evaluate_latency_silence([], transcript)
        # No valid timestamps to compare => no gaps, score = 1.0
        assert result.score == 1.0

    # --- Combined tests ---

    def test_combined_good_latency_good_silence(self) -> None:
        """Both signals healthy."""
        latencies = [500.0, 600.0, 700.0]
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 1.5, 2.5),
            _entry("agent", "Sure", 2.8, 3.5),
        ]
        result = evaluate_latency_silence(latencies, transcript)
        assert result.score == 1.0
        assert result.passed is True

    def test_combined_bad_latency_good_silence(self) -> None:
        """High latency but no silence gaps."""
        latencies = [3000.0] * 5  # p50=3000 => p50_score=0
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "Hi", 1.5, 2.5),
            _entry("agent", "Sure", 2.8, 3.5),
        ]
        result = evaluate_latency_silence(latencies, transcript)
        assert result.raw_output is not None
        # latency_score = 0.5 * 0 + 0.5 * 1 = 0.5, silence_score = 1.0
        # combined = 0.7 * 0.5 + 0.3 * 1.0 = 0.65
        assert result.score == 0.65
        assert result.passed is False

    def test_combined_good_latency_bad_silence(self) -> None:
        """Low latency but silence gaps."""
        latencies = [500.0] * 3
        transcript = [
            _entry("agent", "Hello", 0.0, 1.0),
            _entry("user", "...", 5.0, 5.5),  # 4s gap
        ]
        result = evaluate_latency_silence(latencies, transcript)
        assert result.raw_output is not None
        # latency_score = 1.0, silence_score = 0.0
        # combined = 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert result.score == 0.7
        assert result.passed is True  # exactly 0.7

    def test_single_transcript_entry_no_silence(self) -> None:
        """Single entry: no transitions to check for silence."""
        transcript = [_entry("agent", "Hello", 0.0, 1.0)]
        result = evaluate_latency_silence([], transcript)
        # Single entry, no transitions => only latency (empty) => 1.0
        assert result.score == 1.0

    def test_raw_output_populated(self) -> None:
        """Verify raw_output includes expected fields."""
        latencies = [1000.0, 2000.0, 1500.0]
        transcript = [
            _entry("agent", "A", 0.0, 1.0),
            _entry("user", "B", 5.0, 5.5),
            _entry("agent", "C", 6.0, 7.0),
        ]
        result = evaluate_latency_silence(latencies, transcript)
        assert result.raw_output is not None
        assert "p50_ms" in result.raw_output
        assert "p95_ms" in result.raw_output
        assert "turn_count" in result.raw_output
        assert "silence_gaps" in result.raw_output
        assert "silence_gap_count" in result.raw_output
        assert "latency_score" in result.raw_output
        assert "silence_score" in result.raw_output
