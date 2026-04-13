"""Snapshot API routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse

from ._implementation import compute_diff, get_snapshot

snapshots_router = APIRouter(prefix=endpoints.SNAPSHOTS, tags=["snapshots"])

snapshots_router.add_api_route(
    "/{fingerprint}",
    get_snapshot,
    methods=["GET"],
    summary="Get agent config snapshot by fingerprint",
)

snapshots_router.add_api_route(
    ":computeDiff",
    compute_diff,
    methods=["POST"],
    summary="Compute diff between two snapshots",
    responses={404: {"model": ErrorResponse}},
)
