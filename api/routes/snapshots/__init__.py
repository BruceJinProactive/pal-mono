"""Snapshot API routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse

from ._implementation import compute_diff, get_snapshot


class PrettyJSONResponse(JSONResponse):
    """JSONResponse with indented output for readability."""

    def render(self, content: Any) -> bytes:
        return json.dumps(content, indent=2, default=str, ensure_ascii=False).encode(
            "utf-8"
        )


snapshots_router = APIRouter(
    prefix=endpoints.SNAPSHOTS,
    tags=["snapshots"],
    default_response_class=PrettyJSONResponse,
)

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
