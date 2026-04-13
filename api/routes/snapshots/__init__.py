"""Snapshot API routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.routes.endpoints import endpoints

from ._implementation import get_snapshot

snapshots_router = APIRouter(prefix=endpoints.SNAPSHOTS, tags=["snapshots"])

snapshots_router.add_api_route(
    "/{fingerprint}",
    get_snapshot,
    methods=["GET"],
    summary="Get agent config snapshot by fingerprint",
)
