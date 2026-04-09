"""Tests for CallMetricsReport schema parsing and latency average computation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.internal.voice_init import (
    CallMetricsReport,
    InterruptionEvent,
    TurnLatency,
    VoiceEndCallRequest,
)
from api.schemas.internal.voice_metrics import (
    compute_latency_averages,
    extract_interruption_dicts,
    extract_turn_latency_totals,
    extract_turn_timestamps,
)

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestCallMetricsReportSchema:
    """Validate that the Pydantic schema correctly parses livekit worker payloads."""

    def test_parses_full_metrics_payload(self) -> None:
        raw = {
            "turn_latencies_ms": [
                {
                    "turn_index": 0,
                    "timestamp": 1000.0,
                    "stt_duration_ms": 120.0,
                    "llm_duration_ms": 350.0,
                    "llm_ttft_ms": 80.0,
                    "tts_duration_ms": 200.0,
                },
            ],
            "interruption_events": [
                {"turn_index": 0, "timestamp": 1001.0, "source": "tts"},
            ],
        }
        report = CallMetricsReport.model_validate(raw)
        assert len(report.turn_latencies_ms) == 1
        assert report.turn_latencies_ms[0].stt_duration_ms == 120.0
        assert len(report.interruption_events) == 1
        assert report.interruption_events[0].source == "tts"

    def test_defaults_to_empty_lists(self) -> None:
        report = CallMetricsReport.model_validate({})
        assert report.turn_latencies_ms == []
        assert report.interruption_events == []

    def test_turn_latency_defaults(self) -> None:
        turn = TurnLatency.model_validate({"turn_index": 0, "timestamp": 100.0})
        assert turn.stt_duration_ms == 0.0
        assert turn.llm_duration_ms == 0.0
        assert turn.tts_duration_ms == 0.0
        assert turn.llm_ttft_ms == 0.0
        assert turn.llm_tokens_per_second == 0.0
        assert turn.llm_prompt_tokens == 0
        assert turn.llm_completion_tokens == 0
        assert turn.tts_ttfb_ms == 0.0

    def test_turn_latency_requires_index_and_timestamp(self) -> None:
        with pytest.raises(ValidationError):
            TurnLatency.model_validate({})

    def test_interruption_event_requires_all_fields(self) -> None:
        with pytest.raises(ValidationError):
            InterruptionEvent.model_validate({"turn_index": 0})

    def test_negative_turn_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TurnLatency.model_validate({"turn_index": -1, "timestamp": 100.0})

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TurnLatency.model_validate(
                {"turn_index": 0, "timestamp": 100.0, "stt_duration_ms": -5.0}
            )

    def test_negative_timestamp_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TurnLatency.model_validate({"turn_index": 0, "timestamp": -1.0})

    def test_invalid_interruption_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterruptionEvent.model_validate(
                {"turn_index": 0, "timestamp": 100.0, "source": "invalid"}
            )


class TestVoiceEndCallRequestMetricsField:
    """VoiceEndCallRequest should accept optional metrics."""

    def _base_payload(self) -> dict:
        return {
            "call_id": "test-call-123",
            "caller_number": "+11234567890",
            "dialed_number": "+10987654321",
            "duration_seconds": 42.5,
            "conversation": [],
            "close_reason": "customer_ended",
        }

    def test_metrics_none_by_default(self) -> None:
        req = VoiceEndCallRequest.model_validate(self._base_payload())
        assert req.metrics is None

    def test_metrics_parsed_when_present(self) -> None:
        payload = self._base_payload()
        payload["metrics"] = {
            "turn_latencies_ms": [
                {"turn_index": 0, "timestamp": 100.0, "stt_duration_ms": 50.0},
            ],
            "interruption_events": [],
        }
        req = VoiceEndCallRequest.model_validate(payload)
        assert req.metrics is not None
        assert len(req.metrics.turn_latencies_ms) == 1

    def test_metrics_explicit_none(self) -> None:
        payload = self._base_payload()
        payload["metrics"] = None
        req = VoiceEndCallRequest.model_validate(payload)
        assert req.metrics is None


# ---------------------------------------------------------------------------
# compute_latency_averages (production import from _metrics.py)
# ---------------------------------------------------------------------------


class TestComputeLatencyAverages:
    """Unit tests for the latency average computation helper."""

    def test_empty_report_returns_all_none(self) -> None:
        report = CallMetricsReport(turn_latencies_ms=[], interruption_events=[])
        result = compute_latency_averages(report)
        assert result["turn_latency_avg"] is None
        assert result["model_latency_avg"] is None
        assert result["voice_latency_avg"] is None
        assert result["transcriber_latency_avg"] is None
        assert result["endpointing_latency_avg"] is None

    def test_single_turn_averages(self) -> None:
        turn = TurnLatency(
            turn_index=0,
            timestamp=100.0,
            stt_duration_ms=100.0,
            llm_duration_ms=300.0,
            llm_ttft_ms=80.0,
            tts_duration_ms=200.0,
        )
        report = CallMetricsReport(turn_latencies_ms=[turn])
        result = compute_latency_averages(report)

        # turn_latency_avg = (100 + 300 + 200) ms / 1 / 1000 = 0.6 seconds
        assert result["turn_latency_avg"] == pytest.approx(0.6)
        # model_latency_avg = 300 ms
        assert result["model_latency_avg"] == pytest.approx(300.0)
        # voice_latency_avg = 200 ms
        assert result["voice_latency_avg"] == pytest.approx(200.0)
        # transcriber_latency_avg = 100 ms
        assert result["transcriber_latency_avg"] == pytest.approx(100.0)
        # endpointing_latency_avg = 80 ms
        assert result["endpointing_latency_avg"] == pytest.approx(80.0)

    def test_multi_turn_averages(self) -> None:
        turns = [
            TurnLatency(
                turn_index=0,
                timestamp=100.0,
                stt_duration_ms=100.0,
                llm_duration_ms=300.0,
                llm_ttft_ms=80.0,
                tts_duration_ms=200.0,
            ),
            TurnLatency(
                turn_index=1,
                timestamp=110.0,
                stt_duration_ms=200.0,
                llm_duration_ms=400.0,
                llm_ttft_ms=120.0,
                tts_duration_ms=300.0,
            ),
        ]
        report = CallMetricsReport(turn_latencies_ms=turns)
        result = compute_latency_averages(report)

        # turn_latency_avg = avg((100+300+200), (200+400+300)) ms / 1000
        # = avg(600, 900) / 1000 = 750 / 1000 = 0.75 seconds
        assert result["turn_latency_avg"] == pytest.approx(0.75)
        # model_latency_avg = (300 + 400) / 2 = 350 ms
        assert result["model_latency_avg"] == pytest.approx(350.0)
        # voice_latency_avg = (200 + 300) / 2 = 250 ms
        assert result["voice_latency_avg"] == pytest.approx(250.0)
        # transcriber_latency_avg = (100 + 200) / 2 = 150 ms
        assert result["transcriber_latency_avg"] == pytest.approx(150.0)
        # endpointing_latency_avg = (80 + 120) / 2 = 100 ms
        assert result["endpointing_latency_avg"] == pytest.approx(100.0)

    def test_zero_latencies_produce_zero_not_none(self) -> None:
        turn = TurnLatency(turn_index=0, timestamp=100.0)
        report = CallMetricsReport(turn_latencies_ms=[turn])
        result = compute_latency_averages(report)

        assert result["turn_latency_avg"] == 0.0
        assert result["model_latency_avg"] == 0.0
        assert result["voice_latency_avg"] == 0.0
        assert result["transcriber_latency_avg"] == 0.0
        assert result["endpointing_latency_avg"] == 0.0


# ---------------------------------------------------------------------------
# Event preparation helpers (extract_* functions)
# ---------------------------------------------------------------------------


class TestExtractTurnLatencyTotals:
    """Unit tests for per-turn total latency extraction."""

    def test_empty_report(self) -> None:
        report = CallMetricsReport()
        assert extract_turn_latency_totals(report) == []

    def test_single_turn(self) -> None:
        turn = TurnLatency(
            turn_index=0,
            timestamp=1000.0,
            stt_duration_ms=100.0,
            llm_duration_ms=300.0,
            tts_duration_ms=200.0,
        )
        report = CallMetricsReport(turn_latencies_ms=[turn])
        assert extract_turn_latency_totals(report) == [600.0]

    def test_multi_turn(self) -> None:
        turns = [
            TurnLatency(
                turn_index=0,
                timestamp=1000.0,
                stt_duration_ms=100.0,
                llm_duration_ms=300.0,
                tts_duration_ms=200.0,
            ),
            TurnLatency(
                turn_index=1,
                timestamp=1010.0,
                stt_duration_ms=50.0,
                llm_duration_ms=400.0,
                tts_duration_ms=150.0,
            ),
        ]
        report = CallMetricsReport(turn_latencies_ms=turns)
        assert extract_turn_latency_totals(report) == [600.0, 600.0]


class TestExtractInterruptionDicts:
    """Unit tests for interruption event serialisation."""

    def test_empty_report(self) -> None:
        report = CallMetricsReport()
        assert extract_interruption_dicts(report) == []

    def test_serialises_interruptions(self) -> None:
        report = CallMetricsReport(
            interruption_events=[
                InterruptionEvent(turn_index=0, timestamp=1001.0, source="tts"),
                InterruptionEvent(turn_index=1, timestamp=1011.0, source="llm"),
            ]
        )
        result = extract_interruption_dicts(report)
        assert result == [
            {"turn_index": 0, "timestamp": 1001.0, "source": "tts"},
            {"turn_index": 1, "timestamp": 1011.0, "source": "llm"},
        ]


class TestExtractTurnTimestamps:
    """Unit tests for timestamp extraction."""

    def test_empty_report(self) -> None:
        report = CallMetricsReport()
        assert extract_turn_timestamps(report) == []

    def test_extracts_timestamps_in_order(self) -> None:
        turns = [
            TurnLatency(turn_index=0, timestamp=1000.0),
            TurnLatency(turn_index=1, timestamp=1010.0),
            TurnLatency(turn_index=2, timestamp=1025.0),
        ]
        report = CallMetricsReport(turn_latencies_ms=turns)
        assert extract_turn_timestamps(report) == [1000.0, 1010.0, 1025.0]
