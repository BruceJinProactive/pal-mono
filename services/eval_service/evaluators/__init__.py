"""Evaluators for the eval service.

- tool_call: Deterministic tool call verification (local)
- interruption: E14 interruption detection from transcript timestamps
- latency_silence: E15 latency/silence scoring from turn metrics
- stt_accuracy: E16 STT accuracy / WER via Whisper reference transcription
- speech_rate: E17 TTS speech rate (WPM) scoring
- audio_quality: E17b basic audio signal quality (SNR, clipping)
- speech_fidelity: E18 LLM-as-judge TTS naturalness and spoken delivery quality
- deepeval_adapter: pal-agents DeepEval metrics (faithfulness, responsive,
  voice_appropriate, task_completion)
"""

from services.eval_service.evaluators.audio_quality import evaluate_audio_quality
from services.eval_service.evaluators.deepeval_adapter import (
    evaluate_faithfulness,
    evaluate_responsive,
    evaluate_task_completion,
    evaluate_voice_appropriate,
)
from services.eval_service.evaluators.interruption import evaluate_interruptions
from services.eval_service.evaluators.latency_silence import evaluate_latency_silence
from services.eval_service.evaluators.speech_fidelity import evaluate_speech_fidelity
from services.eval_service.evaluators.speech_rate import evaluate_speech_rate
from services.eval_service.evaluators.stt_accuracy import (
    compute_wer,
    evaluate_stt_accuracy,
    extract_primary_transcript,
)
from services.eval_service.evaluators.tool_call import evaluate_tool_calls

__all__ = [
    "compute_wer",
    "evaluate_audio_quality",
    "evaluate_faithfulness",
    "evaluate_interruptions",
    "evaluate_latency_silence",
    "evaluate_responsive",
    "evaluate_speech_fidelity",
    "evaluate_speech_rate",
    "evaluate_stt_accuracy",
    "evaluate_task_completion",
    "evaluate_tool_calls",
    "evaluate_voice_appropriate",
    "extract_primary_transcript",
]
