"""Agent config snapshot service.

Provides fire-and-forget upsert, lookup, and diff operations for
AgentConfigSnapshot rows.
"""

from __future__ import annotations

import difflib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.agent_config_snapshot_repository import (
    AgentConfigSnapshotRepositoryAsync,
)
from db.session import AsyncSessionLocal
from db.tables import AgentConfigSnapshot
from utils.log import logger


async def upsert_agent_config_snapshot(
    fingerprint: str,
    agent_id: uuid.UUID,
    project_id: uuid.UUID,
    config_dict: dict[str, Any],
    prompt_hash: str,
    prompt_text: str,
) -> None:
    """Upsert an agent config snapshot row.

    Owns its own AsyncSessionLocal — safe for fire-and-forget use from
    background tasks. Swallows all exceptions so callers are never blocked.

    Args:
        fingerprint: SHA-256 hex fingerprint of the agent config.
        agent_id: UUID of the agent.
        project_id: UUID of the project.
        config_dict: Full agent config as a dictionary.
        prompt_hash: SHA-256 hex hash of the system prompt.
        prompt_text: Full system prompt text.
    """
    try:
        async with AsyncSessionLocal() as session:
            snapshot = AgentConfigSnapshot(
                fingerprint=fingerprint,
                agent_id=agent_id,
                project_id=project_id,
                system_prompt_hash=prompt_hash,
                system_prompt_text=prompt_text,
                config_snapshot=config_dict,
            )
            repo = AgentConfigSnapshotRepositoryAsync(session)
            _, created = await repo.get_or_create(snapshot)
            await session.commit()

            if created:
                logger.info(
                    "Created agent config snapshot",
                    extra={
                        "fingerprint": fingerprint[:8],
                        "project_id": str(project_id),
                    },
                )
            else:
                logger.info(
                    "Updated last_seen_at for agent config snapshot",
                    extra={
                        "fingerprint": fingerprint[:8],
                        "project_id": str(project_id),
                    },
                )
    except Exception:
        logger.exception(
            "Failed to upsert agent config snapshot",
            extra={"fingerprint": fingerprint[:8] if fingerprint else "N/A"},
        )


async def get_snapshot_by_fingerprint(
    fingerprint: str,
    session: AsyncSession,
) -> AgentConfigSnapshot | None:
    """Retrieve an agent config snapshot by fingerprint."""
    repo = AgentConfigSnapshotRepositoryAsync(session)
    return await repo.get_by_fingerprint(fingerprint)


async def compute_snapshot_diff(
    from_fingerprint: str,
    to_fingerprint: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Compute the diff between two snapshots identified by fingerprint.

    Returns a dict with prompt_diff (unified text diff), config_diff
    (structured JSON changes), and boolean change flags.

    Raises ValueError if either fingerprint is not found.
    """
    repo = AgentConfigSnapshotRepositoryAsync(session)
    from_snap = await repo.get_by_fingerprint(from_fingerprint)
    to_snap = await repo.get_by_fingerprint(to_fingerprint)

    if from_snap is None:
        raise ValueError(f"Snapshot with fingerprint '{from_fingerprint}' not found")
    if to_snap is None:
        raise ValueError(f"Snapshot with fingerprint '{to_fingerprint}' not found")

    prompt_changed = from_snap.system_prompt_hash != to_snap.system_prompt_hash
    prompt_diff = _compute_prompt_diff(
        from_snap.system_prompt_text, to_snap.system_prompt_text
    )
    config_diff = _compute_config_diff(
        from_snap.config_snapshot, to_snap.config_snapshot
    )

    return {
        "from_fingerprint": from_fingerprint,
        "to_fingerprint": to_fingerprint,
        "prompt_changed": prompt_changed,
        "config_changed": len(config_diff) > 0,
        "prompt_diff": prompt_diff,
        "config_diff": config_diff,
    }


def _compute_prompt_diff(from_text: str, to_text: str) -> str:
    """Return unified diff of two prompt texts."""
    if from_text == to_text:
        return ""
    from_lines = from_text.splitlines(keepends=True)
    to_lines = to_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        from_lines, to_lines, fromfile="from_prompt", tofile="to_prompt"
    )
    return "".join(diff)


def _compute_config_diff(
    from_config: dict[str, Any], to_config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return list of {path, from, to} for leaf-level config changes."""
    changes: list[dict[str, Any]] = []
    _diff_dicts("", from_config, to_config, changes)
    return changes


def _diff_dicts(
    prefix: str,
    old: dict[str, Any],
    new: dict[str, Any],
    changes: list[dict[str, Any]],
) -> None:
    """Recursively diff two dicts, appending changes."""
    all_keys = set(old.keys()) | set(new.keys())
    for key in sorted(all_keys):
        path = f"{prefix}.{key}" if prefix else key
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val == new_val:
            continue
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            _diff_dicts(path, old_val, new_val, changes)
        else:
            changes.append({"path": path, "from": old_val, "to": new_val})
