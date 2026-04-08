"""Prompt traceability service — history and diff logic."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.repositories.agent_config_snapshot_repository import (
    AgentConfigSnapshotRepositoryAsync,
)


async def get_conversation_history_with_prompts(
    project_id: uuid.UUID,
    limit: int,
    session: AsyncSession,
) -> dict[str, Any]:
    """Fetch last N conversations for a project with prompt text and change detection."""
    conversation_repo = db.ConversationRepositoryAsync(session)
    snapshot_repo = AgentConfigSnapshotRepositoryAsync(session)

    conversations = await conversation_repo.get_by_project(project_id, limit=limit)

    # Batch-load snapshots for distinct fingerprints
    fingerprints = {c.agent_fingerprint for c in conversations if c.agent_fingerprint}
    snapshots: dict[str, db.tables.AgentConfigSnapshot] = {}
    for fp in fingerprints:
        snap = await snapshot_repo.get_by_fingerprint(fp)
        if snap:
            snapshots[fp] = snap

    # Build response with prompt_changed flags (oldest-first for comparison)
    results: list[dict[str, Any]] = []
    prev_prompt_hash: str | None = None

    for conv in reversed(conversations):
        snap = snapshots.get(conv.agent_fingerprint) if conv.agent_fingerprint else None
        current_prompt_hash = snap.system_prompt_hash if snap else None

        prompt_changed = (
            prev_prompt_hash is not None
            and current_prompt_hash is not None
            and current_prompt_hash != prev_prompt_hash
        )

        results.append(
            {
                "conversation_id": str(conv.id),
                "agent_fingerprint": conv.agent_fingerprint,
                "prompt_fingerprint": snap.system_prompt_hash if snap else None,
                "prompt_text": snap.system_prompt_text if snap else None,
                "prompt_changed": prompt_changed,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
            }
        )

        if current_prompt_hash:
            prev_prompt_hash = current_prompt_hash

    results.reverse()  # newest first
    return {"project_id": str(project_id), "conversations": results}
