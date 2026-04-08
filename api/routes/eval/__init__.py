"""Eval API routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.endpoints import endpoints

from ._implementation import (
    get_eval_run_with_results,
    get_project_scorecard,
    trigger_eval_run,
)

eval_router = APIRouter(prefix=endpoints.EVAL, tags=["eval"])

eval_router.add_api_route(
    "/run",
    trigger_eval_run,
    methods=["POST"],
    status_code=202,
    summary="Trigger an evaluation run",
)
eval_router.add_api_route(
    "/runs/{run_id}",
    get_eval_run_with_results,
    methods=["GET"],
    summary="Get eval run status and results",
)
eval_router.add_api_route(
    "/scorecard/{project_id}",
    get_project_scorecard,
    methods=["GET"],
    summary="Get aggregated scorecard for a project",
)
