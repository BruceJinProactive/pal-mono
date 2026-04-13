"""Snapshot route handlers — thin delegation to eval service."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.eval.requests import ComputeSnapshotDiffRequest
from api.schemas.eval.responses import SnapshotDiffResponse, SnapshotResponse
from services.eval_service._snapshot import (
    compute_snapshot_diff,
    get_snapshot_by_fingerprint,
)


async def get_snapshot(
    fingerprint: str,
    session: AsyncSession = Depends(db.get_db_async),
) -> SnapshotResponse:
    """Retrieve the full agent config snapshot for a fingerprint.

    Returns the system prompt text, config dictionary, and metadata
    for the exact agent configuration identified by this fingerprint.
    """
    snapshot = await get_snapshot_by_fingerprint(fingerprint, session)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot with fingerprint '{fingerprint}' not found",
            headers={"Content-Type": "application/json"},
        )
    return SnapshotResponse.model_validate(snapshot)


async def compute_diff(
    request: ComputeSnapshotDiffRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> SnapshotDiffResponse:
    """Compute the diff between two agent config snapshots.

    Accepts two fingerprints and returns a unified text diff of the
    system prompt and a structured JSON diff of the config snapshot.
    """
    try:
        result = await compute_snapshot_diff(
            from_fingerprint=request.from_fingerprint,
            to_fingerprint=request.to_fingerprint,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    return SnapshotDiffResponse(**result)
