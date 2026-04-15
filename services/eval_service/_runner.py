"""Background task runner for evaluation runs.

Orchestrates scenario loading, driver construction, conversation execution,
evaluator invocation, and result storage.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
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
from services.eval_service._scenario_loader import load_scenarios
from services.eval_service._user_simulator import END_SENTINEL, UserSimulator
from services.eval_service.schema import EvalScenario, TurnType, UserTurn
from utils.log import logger

# GC prevention for background tasks
_background_tasks: set[asyncio.Task[object]] = set()


async def create_eval_run(
    project_id: uuid.UUID,
    account_id: uuid.UUID,
    channel_identifier: str,
    driver_mode: str,
    triggered_by: str,
    session: AsyncSession,
) -> EvalRun:
    """Create a new eval run and schedule its background execution.

    Args:
        project_id: Project to evaluate.
        account_id: Account that owns the project.
        channel_identifier: Channel identifier for routing (e.g. "api:pokeworks-san_jose").
        driver_mode: "http" or "direct".
        triggered_by: Who triggered the run (e.g. "api", "schedule").
        session: Database session for creating the run row.

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

    _schedule_eval_background(run.id, project_id, channel_identifier, driver_mode)
    return run


def _schedule_eval_background(
    eval_run_id: uuid.UUID,
    project_id: uuid.UUID,
    channel_identifier: str,
    driver_mode: str,
) -> None:
    """Fire-and-forget background task for running evaluation."""
    task = asyncio.create_task(
        _run_eval_background(eval_run_id, project_id, channel_identifier, driver_mode),
        name=f"eval-run-{eval_run_id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_eval_background(
    eval_run_id: uuid.UUID,
    project_id: uuid.UUID,
    channel_identifier: str,
    driver_mode: str,
) -> None:
    """Execute an evaluation run in the background.

    Owns its own AsyncSessionLocal. Updates status through the lifecycle:
    pending -> running -> completed/failed.
    """
    async with AsyncSessionLocal() as session:
        run_repo = EvalRunRepositoryAsync(session)
        result_repo = EvalResultRepositoryAsync(session)

        try:
            # Mark running
            await run_repo.update_status(
                eval_run_id, "running", started_at=datetime.now(timezone.utc)
            )
            await session.commit()

            # Load scenarios
            scenarios = load_scenarios(str(project_id))
            if not scenarios:
                scenarios = load_scenarios()  # Fall back to generic

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

            for scenario in scenarios:
                try:
                    record = await _run_scenario_for_mode(
                        driver_mode, scenario, session, recipient_id, channel
                    )
                    eval_results = await evaluate_scenario(record)

                    # Write results
                    for er in eval_results:
                        db_result = EvalResult(
                            id=uuid.uuid4(),
                            eval_run_id=eval_run_id,
                            scenario_id=scenario.scenario_id,
                            metric_name=er.metric_name,
                            score=er.score,
                            passed=er.passed,
                            reason=er.reason,
                            raw_output=er.raw_output,
                        )
                        await result_repo.create(db_result)

                    scenario_passed = all(er.passed for er in eval_results)
                    if scenario_passed:
                        passed_count += 1
                    else:
                        failed_count += 1

                    # Commit per-scenario for progress visibility
                    await session.commit()

                    logger.info(
                        "Scenario %s completed: passed=%s",
                        scenario.scenario_id,
                        scenario_passed,
                        extra={"eval_run_id": str(eval_run_id)},
                    )

                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Scenario %s failed",
                        scenario.scenario_id,
                        extra={"eval_run_id": str(eval_run_id)},
                    )
                    failed_count += 1

            # Update final counts and status
            total = len(scenarios)
            overall_score = passed_count / total if total > 0 else 0.0
            await run_repo.update_counts(
                eval_run_id,
                scenario_count=total,
                passed_count=passed_count,
                failed_count=failed_count,
                overall_score=overall_score,
            )
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
        return await run_voice_scenario(scenario, voice_config, session)

    driver = create_driver(driver_mode, recipient_id, channel=channel)
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

    for turn_number, turn in enumerate(scenario.user_turns):
        if isinstance(turn, UserTurn) and turn.type == TurnType.AI_DRIVEN:
            message = await simulator.generate_user_message(
                persona=scenario.persona,
                scenario=scenario.scenario,
                goal=turn.goal or "",
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
