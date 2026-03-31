"""Agent config snapshot upsert service.

Fire-and-forget background task that upserts an AgentConfigSnapshot row
after fingerprints are computed during voice call init.
"""

from __future__ import annotations

import uuid
from typing import Any

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
