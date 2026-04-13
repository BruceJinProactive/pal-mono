"""Snapshot route handlers — thin delegation to eval service."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.eval.responses import SnapshotResponse
from services.eval_service._snapshot import get_snapshot_by_fingerprint


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
