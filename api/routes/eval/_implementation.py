"""Eval route handlers — thin delegation to eval service."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
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
    create_eval_run,
    get_eval_results,
    get_eval_run,
    get_scorecard,
)


async def trigger_eval_run(
    request: RunEvalRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> EvalRunResponse:
    """Trigger an evaluation run for a project.

    Creates the run row, kicks off background execution, and returns 202 immediately.
    """
    run = await create_eval_run(
        project_id=request.project_id,
        account_id=request.account_id,
        driver_mode=request.driver,
        triggered_by=request.triggered_by,
        session=session,
    )
    return EvalRunResponse.model_validate(run)


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
