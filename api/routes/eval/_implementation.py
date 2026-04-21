"""Eval route handlers — thin delegation to eval service."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.eval.requests import RunEvalRequest
from api.schemas.eval.responses import (
    EvalResultResponse,
    EvalRunResponse,
    EvalRunWithResultsResponse,
    ScorecardResponse,
)
from services.eval_service._runner import (
    cancel_eval_run,
    create_eval_run,
    get_eval_results,
    get_eval_run,
    get_scorecard,
    list_eval_runs,
    resolve_scenario_info,
)


async def trigger_eval_run(
    request: RunEvalRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> EvalRunResponse:
    """Trigger an evaluation run for a project.

    Creates a run row, kicks off background execution, and returns 202
    immediately with the resolved scenario directories and files.
    Poll GET /v1/eval/runs/{run_id} for results.
    """
    scenario_info = resolve_scenario_info(request.project_id)

    run = await create_eval_run(
        project_id=request.project_id,
        account_id=request.account_id,
        channel_identifier=request.channel_identifier,
        driver_mode=request.driver,
        triggered_by=request.triggered_by,
        session=session,
    )
    response = EvalRunResponse.model_validate(run)
    response.scenario_files = scenario_info["scenario_files"]
    return response


async def get_eval_run_with_results(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(db.get_db_async),
) -> EvalRunWithResultsResponse:
    """Get eval run status and results."""
    run = await get_eval_run(run_id, session)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Eval run {run_id} not found",
        )
    results = await get_eval_results(run_id, session)
    return EvalRunWithResultsResponse(
        run=EvalRunResponse.model_validate(run),
        results=[EvalResultResponse.model_validate(r) for r in results],
    )


async def get_project_scorecard(
    project_id: uuid.UUID,
    limit: int = 10,
    session: AsyncSession = Depends(db.get_db_async),
) -> ScorecardResponse:
    """Get aggregated scorecard for a project's recent eval runs."""
    if limit < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be greater than 0",
        )
    data = await get_scorecard(project_id, session, limit=limit)
    return ScorecardResponse(**data)


async def list_eval_runs_handler(
    status_filter: str | None = Query(
        default=None, alias="status", description="Filter by run status"
    ),
    project_id: uuid.UUID | None = Query(
        default=None, description="Filter by project UUID"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    session: AsyncSession = Depends(db.get_db_async),
) -> list[EvalRunResponse]:
    """List eval runs with optional filters."""
    runs = await list_eval_runs(
        session, status=status_filter, project_id=project_id, limit=limit
    )
    return [EvalRunResponse.model_validate(r) for r in runs]


async def cancel_eval_run_handler(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(db.get_db_async),
) -> EvalRunResponse:
    """Cancel a running or pending eval run."""
    try:
        run = await cancel_eval_run(run_id, session)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=msg,
        )
    return EvalRunResponse.model_validate(run)
