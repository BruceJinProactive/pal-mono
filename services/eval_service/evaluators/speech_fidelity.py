"""E18: Speech fidelity LALM-as-Judge evaluator.

Assesses the naturalness, pronunciation quality, pacing, and
conversational tone of the agent's TTS output using an LLM judge.

Operates on transcript text (no audio model required).  The LLM
evaluates whether the agent's responses *read* as natural spoken
language — short sentences, no jargon dumps, proper turn-taking, and
conversational cadence.

Uses DeepEval GEval with a rubric scored by the shared EVAL_MODEL
(Claude Sonnet 4 via Bedrock) for consistency with other LLM-judged
metrics.
"""

from __future__ import annotations

import asyncio

from deepeval.metrics import GEval
from deepeval.metrics.g_eval.utils import Rubric
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from pal_agents.evals.metrics import EVAL_MODEL

from services.eval_service._evaluators import ConversationRecord, EvaluatorResult
from utils.log import logger

_METRIC_NAME = "speech_fidelity"
_THRESHOLD = 0.7
_JUDGE_TIMEOUT_S = 60.0  # max seconds for the LLM judge call


def _create_speech_fidelity_metric() -> GEval:
    """Build a GEval metric with a speech-fidelity rubric.

    The rubric evaluates whether agent responses are suitable for
    text-to-speech delivery: short sentences, natural phrasing,
    no visual formatting, and good conversational cadence.
    """
    return GEval(
        name="Speech Fidelity",
        criteria="""
        Evaluate whether the assistant's responses are well-suited for
        spoken delivery via text-to-speech (TTS).

        Consider these dimensions:

        1. NATURALNESS — Do responses sound like natural spoken language?
           Contractions, conversational phrasing, and sentence fragments
           are fine.  Stiff, overly formal, or robotic phrasing is bad.

        2. PRONUNCIATION FRIENDLINESS — Are responses free of content that
           TTS engines struggle with?  Problematic patterns:
           - Abbreviations without expansion (e.g., "approx.", "misc.")
           - Bare URLs, email addresses, or file paths read aloud
           - Dense numeric strings or codes (e.g., "SKU-29481-X")
           - Special characters or symbols (e.g., "&", "#", "@")
           - Markdown or HTML formatting (e.g., "**bold**", bullet lists)

        3. PACING / BREVITY — Are responses concise enough for voice?
           - Good: 1-3 short sentences per turn
           - Bad: long monologues, run-on sentences, walls of text
           - Voice conversations demand shorter turns than chat

        4. CONVERSATIONAL TONE — Does the agent maintain a warm,
           helpful, human-like tone throughout?  Overly verbose
           disclaimers, legalese, or corporate jargon are penalized.
        """,
        evaluation_steps=[
            "Read the assistant's responses in 'actual output' as if they "
            "would be spoken aloud by a TTS engine",
            "Check for naturalness: do responses sound like a human speaking?",
            "Check for TTS-hostile content: abbreviations, URLs, special "
            "characters, markdown formatting, dense numbers",
            "Check pacing: are responses appropriately brief for voice?",
            "Check tone: warm, conversational, not robotic or overly formal",
            "A response can be brief and still score high if it sounds natural",
        ],
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=EVAL_MODEL,
        threshold=_THRESHOLD,
        rubric=[
            Rubric(
                score_range=(0, 2),
                expected_outcome=(
                    "Responses are clearly unsuitable for TTS: contain markdown, "
                    "URLs, dense numbers, or read like written text, not speech"
                ),
            ),
            Rubric(
                score_range=(3, 4),
                expected_outcome=(
                    "Responses have multiple TTS issues: overly long turns, "
                    "some abbreviations or formatting, stiff phrasing"
                ),
            ),
            Rubric(
                score_range=(5, 6),
                expected_outcome=(
                    "Responses are mostly speakable but have occasional issues: "
                    "one or two long turns, minor formatting artifacts, "
                    "slightly formal tone"
                ),
            ),
            Rubric(
                score_range=(7, 8),
                expected_outcome=(
                    "Responses sound natural when read aloud with minor "
                    "improvements possible: slightly long in places or "
                    "one instance of TTS-unfriendly content"
                ),
            ),
            Rubric(
                score_range=(9, 10),
                expected_outcome=(
                    "Responses are perfectly suited for TTS: concise, natural, "
                    "warm tone, no formatting artifacts, sound like a human "
                    "speaking in a phone conversation"
                ),
            ),
        ],
    )


def _format_conversation(record: ConversationRecord) -> tuple[str, str]:
    """Extract user input and agent output from the conversation record.

    Returns:
        Tuple of (combined_user_input, combined_agent_output).
    """
    user_parts: list[str] = []
    agent_parts: list[str] = []

    for turn in record.turns:
        user_msg = turn.get("user", "")
        agent_msg = turn.get("assistant", "")
        if user_msg:
            user_parts.append(user_msg)
        if agent_msg:
            agent_parts.append(agent_msg)

    # Fall back to agent_responses if turns don't have assistant keys
    if not agent_parts and record.agent_responses:
        agent_parts = list(record.agent_responses)

    return " ".join(user_parts), " ".join(agent_parts)


async def evaluate_speech_fidelity(
    record: ConversationRecord,
) -> EvaluatorResult:
    """E18: Judge speech fidelity of agent TTS output.

    Uses an LLM judge (GEval with rubric) to score whether the agent's
    responses are well-suited for spoken delivery: natural phrasing,
    TTS-friendly content, appropriate brevity, and conversational tone.

    Args:
        record: The completed conversation record to evaluate.

    Returns:
        EvaluatorResult with score in [0, 1] and LLM judge reasoning.
    """
    user_input, agent_output = _format_conversation(record)

    if not agent_output.strip():
        return EvaluatorResult(
            metric_name=_METRIC_NAME,
            score=1.0,
            passed=True,
            reason="No agent output to evaluate for speech fidelity",
        )

    metric = _create_speech_fidelity_metric()

    test_case = LLMTestCase(
        input=user_input or "(voice call)",
        actual_output=agent_output,
    )

    try:
        await asyncio.wait_for(metric.a_measure(test_case), timeout=_JUDGE_TIMEOUT_S)
        return EvaluatorResult(
            metric_name=_METRIC_NAME,
            score=metric.score or 0.0,
            passed=metric.is_successful(),
            reason=metric.reason or "No reason provided",
        )
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        logger.warning(
            "Speech fidelity evaluation timed out after %ss", _JUDGE_TIMEOUT_S
        )
        return EvaluatorResult(
            metric_name=_METRIC_NAME,
            score=0.0,
            passed=False,
            reason=f"Speech fidelity evaluation timed out after {_JUDGE_TIMEOUT_S}s",
        )
    except Exception:
        logger.exception("Speech fidelity evaluation failed")
        return EvaluatorResult(
            metric_name=_METRIC_NAME,
            score=0.0,
            passed=False,
            reason="Speech fidelity evaluation failed — see logs for details",
        )
