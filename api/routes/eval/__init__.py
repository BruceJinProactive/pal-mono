"""Eval API routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.endpoints import endpoints

from ._implementation import (
    cancel_eval_run_handler,
    get_eval_run_with_results,
    get_project_scorecard,
    list_eval_runs_handler,
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
    "/runs",
    list_eval_runs_handler,
    methods=["GET"],
    summary="List eval runs with optional filters",
)
eval_router.add_api_route(
    "/runs/{run_id}",
    get_eval_run_with_results,
    methods=["GET"],
    summary="Get eval run status and results",
)
eval_router.add_api_route(
    "/runs/{run_id}/cancel",
    cancel_eval_run_handler,
    methods=["POST"],
    summary="Cancel a running or pending eval run",
)
eval_router.add_api_route(
    "/scorecard/{project_id}",
    get_project_scorecard,
    methods=["GET"],
    summary="Get aggregated scorecard for a project",
)
