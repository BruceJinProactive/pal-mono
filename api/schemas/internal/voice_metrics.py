"""Lightweight helpers for computing call latency metrics.

This module is kept free of heavy imports (no ``db``, ``services``, etc.) so
that it can be imported directly in unit tests without triggering the deep
import chain that ``api.routes.internal._voice`` pulls in.
"""

from __future__ import annotations

from api.schemas.internal.voice_init import CallMetricsReport


def compute_latency_averages(
    report: CallMetricsReport,
) -> dict[str, float | None]:
    """Derive PhoneCall latency averages from a CallMetricsReport.

    Returns a dict with keys matching the PhoneCall latency columns:
    - turn_latency_avg: mean total turn latency in **seconds**
      (STT + LLM + TTS per turn, converted from ms)
    - model_latency_avg: mean LLM duration in **milliseconds**
    - voice_latency_avg: mean TTS duration in **milliseconds**
    - transcriber_latency_avg: mean STT duration in **milliseconds**
    - endpointing_latency_avg: mean LLM TTFT in **milliseconds**

    Values are None when no turns are available.
    """
    turns = report.turn_latencies_ms
    if not turns:
        return {
            "turn_latency_avg": None,
            "model_latency_avg": None,
            "voice_latency_avg": None,
            "transcriber_latency_avg": None,
            "endpointing_latency_avg": None,
        }

    n = len(turns)

    total_turn_ms = sum(
        t.stt_duration_ms + t.llm_duration_ms + t.tts_duration_ms for t in turns
    )
    total_llm_ms = sum(t.llm_duration_ms for t in turns)
    total_tts_ms = sum(t.tts_duration_ms for t in turns)
    total_stt_ms = sum(t.stt_duration_ms for t in turns)
    total_ttft_ms = sum(t.llm_ttft_ms for t in turns)

    return {
        "turn_latency_avg": (total_turn_ms / n) / 1000.0,  # ms → seconds
        "model_latency_avg": total_llm_ms / n,
        "voice_latency_avg": total_tts_ms / n,
        "transcriber_latency_avg": total_stt_ms / n,
        "endpointing_latency_avg": total_ttft_ms / n,
    }
