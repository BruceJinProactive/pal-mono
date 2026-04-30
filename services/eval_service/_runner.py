"""Background task runner for evaluation runs.

Orchestrates scenario loading, driver construction, conversation execution,
evaluator invocation, and result storage.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pal_agents.evals.drivers import ConversationTurn, TurnResult
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.eval_result_repository import EvalResultRepositoryAsync
from db.repositories.eval_run_repository import EvalRunRepositoryAsync
from db.repositories.message_repository import MessageRepositoryAsync
from db.session import AsyncSessionLocal
from db.tables import EvalResult, EvalRun
from services.eval_service._driver_factory import create_driver
from services.eval_service._evaluators import ConversationRecord, evaluate_scenario
from services.eval_service._scenario_loader import (
    load_scenarios,
    validate_scenarios_from_yaml,
)
from services.eval_service._user_simulator import END_SENTINEL, UserSimulator
from services.eval_service.schema import EvalScenario, TurnType, UserTurn
from utils.log import logger

# GC prevention for background tasks
_background_tasks: set[asyncio.Task[object]] = set()

# Default max concurrent scenarios per eval run.
# Callers of ``create_eval_run`` can override by passing ``max_concurrency``.
# Voice mode honours the same knob — each voice scenario owns an isolated
# LiveKit room, orchestrator, TTS engine, and egress pipeline (see
# ``run_voice_scenario``), so concurrency is bounded by caller infra
# (LiveKit worker pool, Cartesia rate limit, STT quota), not by shared
# in-process state. Pick a conservative cap if your worker pool is small.
_DEFAULT_MAX_CONCURRENCY = 4

# Hard upper bound on per-run scenario concurrency. Enforced inside
# ``_resolve_max_concurrency`` so *any* caller (not just the HTTP API,
# which already validates via ``RunEvalRequest.max_concurrency``) cannot
# fan out more workers / sessions than the service is willing to support.
# Must stay in sync with ``RunEvalRequest.max_concurrency``'s ``le=``.
_MAX_CONCURRENCY = 64


def _resolve_max_concurrency(driver_mode: str, max_concurrency: int | None) -> int:
    """Return the effective per-run scenario concurrency cap.

    Use the caller-supplied value if provided, else
    ``_DEFAULT_MAX_CONCURRENCY``. The result is clamped to
    ``[1, _MAX_CONCURRENCY]``. ``driver_mode`` is accepted for future
    mode-specific defaults but is currently unused.
    """
    del driver_mode  # reserved for future per-mode defaults
    if max_concurrency is None:
        return _DEFAULT_MAX_CONCURRENCY
    return min(_MAX_CONCURRENCY, max(1, max_concurrency))


_PROJECT_MAP_PATH = Path(__file__).parent / "scenarios" / "project_map.json"


_SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def _resolve_scenario_files(project_id: uuid.UUID) -> list[str]:
    """Look up scenario file paths for a project_id via project_map.json.

    The map is keyed by project_id (UUID string) and the value is either a
    single file path (str) or a list of file paths, relative to the
    ``scenarios/`` directory (e.g. ``"ordering/marcos_lookup.yaml"``).

    Returns:
        List of file path strings relative to scenarios/, or empty list if
        not found.
    """
    if not _PROJECT_MAP_PATH.exists():
        return []
    with _PROJECT_MAP_PATH.open("r", encoding="utf-8") as fh:
        project_map: dict[str, str | list[str]] = json.load(fh)
    value = project_map.get(str(project_id))
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def resolve_scenario_info(
    project_id: uuid.UUID,
) -> dict[str, list[str]]:
    """Resolve which scenario files will run for a project.

    Returns:
        Dict with "scenario_files" list (paths relative to scenarios/).
    """
    scenario_files = _resolve_scenario_files(project_id)

    if not scenario_files:
        # Fallback: only generic scenarios
        generic_dir = _SCENARIOS_DIR / "generic"
        if generic_dir.exists():
            scenario_files = [
                str(f.relative_to(_SCENARIOS_DIR))
                for f in sorted(generic_dir.rglob("*.yaml"))
                + sorted(generic_dir.rglob("*.yml"))
            ]

    return {
        "scenario_files": scenario_files,
    }


async def create_eval_run(
    project_id: uuid.UUID,
    account_id: uuid.UUID,
    channel_identifier: str,
    driver_mode: str,
    triggered_by: str,
    session: AsyncSession,
    max_concurrency: int | None = None,
) -> EvalRun:
    """Create a new eval run and schedule its background execution.

    Args:
        project_id: Project to evaluate.
        account_id: Account that owns the project.
        channel_identifier: Channel identifier for routing (e.g. "api:pokeworks-san_jose").
        driver_mode: "http" or "direct".
        triggered_by: Who triggered the run (e.g. "api", "schedule").
        session: Database session for creating the run row.
        max_concurrency: Optional cap on parallel scenarios. ``None`` uses
            the module default (see ``_DEFAULT_MAX_CONCURRENCY``). Applies
            uniformly to all driver modes including ``voice`` — callers
            should pick a value appropriate to their LiveKit worker pool
            and TTS/STT rate limits.

    Returns:
        The created EvalRun in "pending" status.
    """
    repo = EvalRunRepositoryAsync(session)
    run = EvalRun(
        id=uuid.uuid4(),
        project_id=project_id,
        account_id=account_id,
        driver_mode=driver_mode,
        status="pending",
        triggered_by=triggered_by,
    )
    run = await repo.create(run)
    await session.commit()
    await session.refresh(run)

    _schedule_eval_background(
        run.id, project_id, channel_identifier, driver_mode, max_concurrency
    )
    return run


def _schedule_eval_background(
    eval_run_id: uuid.UUID,
    project_id: uuid.UUID,
    channel_identifier: str,
    driver_mode: str,
    max_concurrency: int | None = None,
) -> None:
    """Fire-and-forget background task for running evaluation."""
    task = asyncio.create_task(
        _run_eval_background(
            eval_run_id,
            project_id,
            channel_identifier,
            driver_mode,
            max_concurrency,
        ),
        name=f"eval-run-{eval_run_id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_eval_background(
    eval_run_id: uuid.UUID,
    project_id: uuid.UUID,
    channel_identifier: str,
    driver_mode: str,
    max_concurrency: int | None = None,
) -> None:
    """Execute an evaluation run in the background.

    Owns its own AsyncSessionLocal. Updates status through the lifecycle:
    pending -> running -> completed/failed.
    """
    async with AsyncSessionLocal() as session:
        run_repo = EvalRunRepositoryAsync(session)

        try:
            # Mark running
            await run_repo.update_status(
                eval_run_id, "running", started_at=datetime.now(timezone.utc)
            )
            await session.commit()

            # Look up scenario file paths from project_map.json
            scenario_file_paths = _resolve_scenario_files(project_id)
            scenarios: list[EvalScenario] = []
            if scenario_file_paths:
                for file_path in scenario_file_paths:
                    abs_path = _SCENARIOS_DIR / file_path
                    scenarios.extend(validate_scenarios_from_yaml(abs_path))
                logger.info(
                    "Loaded %d scenarios for project %s (files: %s)",
                    len(scenarios),
                    project_id,
                    scenario_file_paths,
                    extra={
                        "project_id": str(project_id),
                        "scenario_files": scenario_file_paths,
                        "scenario_ids": [s.scenario_id for s in scenarios],
                    },
                )
            else:
                logger.warning(
                    "Project %s not found in project_map.json, falling back to generic",
                    project_id,
                )
                scenarios = load_scenarios("generic")

            if not scenarios:
                await run_repo.update_status(
                    eval_run_id,
                    "failed",
                    completed_at=datetime.now(timezone.utc),
                    error_message="No scenarios found",
                )
                await session.commit()
                return

            # Parse caller-provided channel identifier into channel + recipient_id
            channel, recipient_id = _parse_channel_identifier(channel_identifier)

            passed_count = 0
            failed_count = 0
            max_concurrency_effective = _resolve_max_concurrency(
                driver_mode, max_concurrency
            )
            sem = asyncio.Semaphore(max_concurrency_effective)
            counter_lock = asyncio.Lock()

            async def _worker(scenario: EvalScenario) -> None:
                nonlocal passed_count, failed_count
                async with sem:
                    scenario_passed = await _run_one_scenario(
                        scenario,
                        driver_mode,
                        recipient_id,
                        channel,
                        eval_run_id,
                    )
                async with counter_lock:
                    if scenario_passed:
                        passed_count += 1
                    else:
                        failed_count += 1
                    completed = passed_count + failed_count
                    score = passed_count / completed if completed > 0 else 0.0
                    await run_repo.update_counts(
                        eval_run_id,
                        scenario_count=completed,
                        passed_count=passed_count,
                        failed_count=failed_count,
                        overall_score=score,
                    )
                    await session.commit()
                    logger.info(
                        "Scenario %s completed: passed=%s",
                        scenario.scenario_id,
                        scenario_passed,
                        extra={"eval_run_id": str(eval_run_id)},
                    )

            logger.info(
                "Running %d scenarios with max_concurrency=%d (driver_mode=%s)",
                len(scenarios),
                max_concurrency_effective,
                driver_mode,
                extra={"eval_run_id": str(eval_run_id)},
            )
            await asyncio.gather(*(_worker(s) for s in scenarios))

            # Final status update
            total = passed_count + failed_count
            overall_score = passed_count / total if total > 0 else 0.0
            await run_repo.update_status(
                eval_run_id,
                "completed",
                completed_at=datetime.now(timezone.utc),
            )
            await session.commit()

            logger.info(
                "Eval run completed: %s/%s passed (%.1f%%)",
                passed_count,
                total,
                overall_score * 100,
                extra={"eval_run_id": str(eval_run_id)},
            )

        except asyncio.CancelledError:
            logger.info("Eval run cancelled", extra={"eval_run_id": str(eval_run_id)})
            # DB status already set by cancel_eval_run; nothing to overwrite.

        except Exception as exc:
            logger.exception("Eval run failed", extra={"eval_run_id": str(eval_run_id)})
            # Use a separate session for the failure update
            async with AsyncSessionLocal() as err_session:
                err_repo = EvalRunRepositoryAsync(err_session)
                await err_repo.update_status(
                    eval_run_id,
                    "failed",
                    completed_at=datetime.now(timezone.utc),
                    error_message=str(exc)[:500],
                )
                await err_session.commit()


def _parse_channel_identifier(channel_identifier: str) -> tuple[str, str]:
    """Parse a channel identifier string into (channel, recipient_id).

    Args:
        channel_identifier: Colon-separated identifier (e.g. "api:pokeworks-san_jose").

    Returns:
        Tuple of (channel, recipient_id).

    Raises:
        ValueError: If the format is invalid.
    """
    if ":" not in channel_identifier:
        raise ValueError(
            f"Invalid channel_identifier format: {channel_identifier!r}. "
            "Expected 'channel:identifier' (e.g. 'api:pokeworks-san_jose')."
        )
    channel, recipient_id = channel_identifier.split(":", 1)
    if not channel or not recipient_id:
        raise ValueError(
            f"Invalid channel_identifier format: {channel_identifier!r}. "
            "Both channel and identifier must be non-empty."
        )
    return channel, recipient_id


def _infer_customer_phone(scenario: EvalScenario) -> str | None:
    """Extract customer phone from scenario expected_tool_calls.

    Mirrors pal-agents run_loop._infer_customer_phone: checks
    expected_tool_calls[*].args.customer.phone for the first non-empty value.
    """
    for tc in scenario.expected_tool_calls:
        customer = tc.args.get("customer", {})
        phone = str(customer.get("phone", "")).strip()
        if phone:
            return phone
    return None


async def _run_one_scenario(
    scenario: EvalScenario,
    driver_mode: str,
    recipient_id: str,
    channel: str,
    eval_run_id: uuid.UUID,
) -> bool:
    """Run + evaluate one scenario, writing its EvalResult rows.

    Owns its own ``AsyncSessionLocal`` so parallel workers do not contend on
    the outer run-level session (see ADR-019 for the session-ownership
    pattern used by long-lived async work).

    Returns:
        True if every evaluator result for this scenario passed, False if
        any evaluator failed OR the scenario raised before evaluation
        completed (exception is logged here; caller treats it as a failure).
    """
    async with AsyncSessionLocal() as session:
        result_repo = EvalResultRepositoryAsync(session)
        # Stage 1: driver + evaluators. Failures here mark the scenario
        # failed but do NOT fail the whole run — one broken scenario
        # should not poison siblings.
        try:
            record = await _run_scenario_for_mode(
                driver_mode, scenario, session, recipient_id, channel
            )
            eval_results = await evaluate_scenario(record)
        except asyncio.CancelledError:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            logger.exception(
                "Scenario %s failed",
                scenario.scenario_id,
                extra={"eval_run_id": str(eval_run_id)},
            )
            return False

        # Stage 2: persist results. Failures here indicate a broken
        # persistence path (DB down, schema mismatch, etc.) and MUST
        # propagate so the outer runner surfaces the run as failed
        # rather than silently completing with missing rows.
        try:
            conversation_turns = record.turns
            for er in eval_results:
                raw = dict(er.raw_output) if er.raw_output else {}
                raw["conversation"] = conversation_turns
                db_result = EvalResult(
                    id=uuid.uuid4(),
                    eval_run_id=eval_run_id,
                    scenario_id=scenario.scenario_id,
                    metric_name=er.metric_name,
                    score=er.score,
                    passed=er.passed,
                    reason=er.reason,
                    raw_output=raw,
                )
                await result_repo.create(db_result)
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
        return all(er.passed for er in eval_results)


async def _run_scenario_for_mode(
    driver_mode: str,
    scenario: EvalScenario,
    session: AsyncSession,
    recipient_id: str,
    channel: str,
) -> ConversationRecord:
    """Dispatch a scenario to the appropriate runner based on driver mode.

    Voice mode uses the dedicated voice eval pipeline (room injection).
    All other modes use the standard text-based driver + simulator loop.
    """
    if driver_mode == "voice":
        from services.eval_service._voice_eval_runner import (
            VoiceEvalConfig,
            run_voice_scenario,
        )

        voice_config = VoiceEvalConfig.from_env()
        return await run_voice_scenario(
            scenario, voice_config, session, dialed_number=recipient_id
        )

    customer_phone = _infer_customer_phone(scenario)
    driver = create_driver(
        driver_mode,
        recipient_id,
        channel=channel,
        scenario_id=scenario.scenario_id,
        customer_phone=customer_phone,
    )
    simulator = UserSimulator()
    return await _run_conversation(driver, scenario, simulator)


async def _extract_tool_calls_from_db(
    conversation_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Query all tool_calls from messages in a conversation.

    Reads ``messages.body["tool_calls"]`` for every message in the
    conversation and returns a flat list of tool-call event dicts.
    """
    async with AsyncSessionLocal() as session:
        repo = MessageRepositoryAsync(session)
        db_messages = await repo.get_messages_by_conversation(conversation_id)

    tool_calls: list[dict[str, Any]] = []
    for msg in db_messages:
        if msg.body and isinstance(msg.body, dict):
            tc = msg.body.get("tool_calls", [])
            tool_calls.extend(tc)
    return tool_calls


async def _run_conversation(
    driver: Any,
    scenario: EvalScenario,
    simulator: UserSimulator,
) -> ConversationRecord:
    """Execute a conversation with the agent driver for one scenario.

    Handles both static turns (fixed text) and ai_driven turns (generated
    by UserSimulator based on persona, scenario, and goal).

    Args:
        driver: AgentDriver instance.
        scenario: The scenario to run.
        simulator: UserSimulator for ai_driven turns.

    Returns:
        ConversationRecord with all turns and responses.
    """
    record = ConversationRecord(scenario=scenario)
    history: list[ConversationTurn] = []

    is_last_turn = False
    for turn_number, turn in enumerate(scenario.user_turns):
        is_last_turn = turn_number == len(scenario.user_turns) - 1

        if isinstance(turn, UserTurn) and turn.type == TurnType.AI_DRIVEN:
            goal = turn.goal or ""

            if is_last_turn:
                # Last entry: loop the simulator until [END] or max_turns
                remaining = scenario.max_turns - len(history) // 2
                if remaining <= 0:
                    logger.warning(
                        "No turn budget remaining for ai_driven loop in "
                        "scenario %s (max_turns=%d, turns_used=%d). "
                        "Granting 1 turn.",
                        scenario.scenario_id,
                        scenario.max_turns,
                        len(history) // 2,
                    )
                    remaining = 1
                for _ai_turn in range(remaining):
                    message = await simulator.generate_user_message(
                        persona=scenario.persona,
                        scenario=scenario.scenario,
                        goal=goal,
                        conversation_history=history,
                        turn_number=len(history) // 2,
                        max_turns=scenario.max_turns,
                    )
                    if message == END_SENTINEL:
                        logger.info(
                            "Simulator ended conversation at turn %d "
                            "for scenario %s",
                            len(history) // 2,
                            scenario.scenario_id,
                        )
                        break
                    result: TurnResult = await driver.send_turn(message, history)
                    history.append(ConversationTurn(role="user", content=message))
                    history.append(
                        ConversationTurn(role="assistant", content=result.content)
                    )
                    record.turns.append({"user": message, "assistant": result.content})
                    record.agent_responses.append(result.content)
                break  # loop consumed remaining turns
            else:
                # Not last entry: single call (backwards compat)
                message = await simulator.generate_user_message(
                    persona=scenario.persona,
                    scenario=scenario.scenario,
                    goal=goal,
                    conversation_history=history,
                    turn_number=turn_number,
                )
                if message == END_SENTINEL:
                    logger.info(
                        "Simulator ended conversation at turn %d for scenario %s",
                        turn_number,
                        scenario.scenario_id,
                    )
                    break
        elif isinstance(turn, UserTurn):
            message = turn.text or turn.goal or ""
        else:
            message = str(turn)

        result: TurnResult = await driver.send_turn(message, history)

        history.append(ConversationTurn(role="user", content=message))
        history.append(ConversationTurn(role="assistant", content=result.content))

        record.turns.append({"user": message, "assistant": result.content})
        record.agent_responses.append(result.content)

    # After all turns complete, read tool_calls from DB
    if hasattr(driver, "last_conversation_id") and driver.last_conversation_id:
        record.tool_calls = await _extract_tool_calls_from_db(
            uuid.UUID(driver.last_conversation_id)
        )

    return record


async def get_eval_run(
    run_id: uuid.UUID,
    session: AsyncSession,
) -> EvalRun | None:
    """Retrieve an eval run by ID.

    Args:
        run_id: UUID of the eval run.
        session: Database session.

    Returns:
        EvalRun if found, None otherwise.
    """
    repo = EvalRunRepositoryAsync(session)
    return await repo.get_by_id(run_id)


async def get_eval_results(
    run_id: uuid.UUID,
    session: AsyncSession,
) -> list[EvalResult]:
    """Retrieve all results for an eval run.

    Args:
        run_id: UUID of the eval run.
        session: Database session.

    Returns:
        List of EvalResult rows.
    """
    repo = EvalResultRepositoryAsync(session)
    return await repo.get_by_run_id(run_id)


async def get_scorecard(
    project_id: uuid.UUID,
    session: AsyncSession,
    limit: int = 10,
) -> dict[str, Any]:
    """Get a scorecard summary for a project's recent eval runs.

    Args:
        project_id: Project UUID.
        session: Database session.
        limit: Maximum number of runs to include.

    Returns:
        Dict with project_id, runs summary, and aggregate metrics.
    """
    run_repo = EvalRunRepositoryAsync(session)
    result_repo = EvalResultRepositoryAsync(session)

    runs = await run_repo.get_by_project(project_id)
    runs = runs[:limit]

    run_summaries: list[dict[str, Any]] = []
    for run in runs:
        results = await result_repo.get_by_run_id(run.id)
        metrics: dict[str, dict[str, Any]] = {}
        for r in results:
            if r.metric_name not in metrics:
                metrics[r.metric_name] = {"scores": [], "passed_count": 0, "total": 0}
            metrics[r.metric_name]["scores"].append(r.score)
            metrics[r.metric_name]["total"] += 1
            if r.passed:
                metrics[r.metric_name]["passed_count"] += 1

        aggregated = {
            name: {
                "avg_score": sum(m["scores"]) / len(m["scores"]) if m["scores"] else 0,
                "pass_rate": m["passed_count"] / m["total"] if m["total"] > 0 else 0,
            }
            for name, m in metrics.items()
        }

        run_summaries.append(
            {
                "run_id": str(run.id),
                "status": run.status,
                "overall_score": run.overall_score,
                "scenario_count": run.scenario_count,
                "passed_count": run.passed_count,
                "failed_count": run.failed_count,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "metrics": aggregated,
            }
        )

    return {
        "project_id": str(project_id),
        "runs": run_summaries,
    }


async def list_eval_runs(
    session: AsyncSession,
    *,
    status: str | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[EvalRun]:
    """List eval runs with optional filters.

    Args:
        session: Database session.
        status: Optional status filter (e.g. 'running', 'pending').
        project_id: Optional project UUID filter.
        limit: Maximum number of runs to return.

    Returns:
        List of EvalRun rows ordered by created_at descending.
    """
    repo = EvalRunRepositoryAsync(session)
    return await repo.get_all(status=status, project_id=project_id, limit=limit)


async def cancel_eval_run(
    run_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    """Cancel a running or pending eval run.

    Marks the run as failed in the DB and cancels the background asyncio task
    if it is executing on this process.

    Args:
        run_id: UUID of the eval run to cancel.
        session: Database session.

    Raises:
        ValueError: If the run is not found or is already in a terminal state.
    """
    repo = EvalRunRepositoryAsync(session)
    run = await repo.get_by_id(run_id)
    if run is None:
        raise ValueError(f"Eval run {run_id} not found")

    if run.status in ("completed", "failed"):
        raise ValueError(
            f"Eval run {run_id} is already {run.status} and cannot be cancelled"
        )

    # Cancel the asyncio task if it's on this instance
    task_name = f"eval-run-{run_id}"
    target = next(
        (t for t in _background_tasks if t.get_name() == task_name),
        None,
    )
    if target is not None:
        target.cancel()

    # Mark as failed in DB
    await repo.update_status(
        run_id,
        "failed",
        completed_at=datetime.now(timezone.utc),
        error_message="Cancelled by user",
    )
    await session.commit()


async def mark_stale_runs_failed(
    session: AsyncSession,
    stale_minutes: int = 30,
) -> int:
    """Mark runs stuck in 'running' status as failed.

    Args:
        session: Database session.
        stale_minutes: Minutes after which a running run is considered stale.

    Returns:
        Number of runs marked as failed.
    """
    run_repo = EvalRunRepositoryAsync(session)
    # Get all running runs across all projects
    from sqlalchemy import select

    from db.tables import EvalRun as EvalRunTable

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=stale_minutes)
    stmt = select(EvalRunTable).filter(
        EvalRunTable.status == "running",
        EvalRunTable.started_at <= stale_cutoff,
    )
    result = await session.execute(stmt)
    stale_runs = list(result.scalars().all())

    count = 0
    for run in stale_runs:
        await run_repo.update_status(
            run.id,
            "failed",
            completed_at=now,
            error_message=f"Stale run: no progress for {stale_minutes} minutes",
        )
        count += 1

    if count > 0:
        await session.commit()
        logger.info("Marked %d stale eval runs as failed", count)

    return count
