from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.agent_config_snapshot import AgentConfigSnapshotData
from db.tables.agent_config_snapshots import AgentConfigSnapshot
from utils.log import logger


def _to_data(row: AgentConfigSnapshot) -> AgentConfigSnapshotData:
    """Convert an ORM AgentConfigSnapshot to an AgentConfigSnapshotData."""
    return AgentConfigSnapshotData(
        fingerprint=row.fingerprint,
        agent_id=row.agent_id,
        project_id=row.project_id,
        system_prompt_hash=row.system_prompt_hash,
        system_prompt_text=row.system_prompt_text,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        config_snapshot=dict(row.config_snapshot) if row.config_snapshot else {},
    )


class AgentConfigSnapshotRepository:
    """Async-only repository for AgentConfigSnapshot records.

    All methods return ``AgentConfigSnapshotData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_fingerprint(
        self, fingerprint: str
    ) -> AgentConfigSnapshotData | None:
        """Retrieve a snapshot by its fingerprint."""
        try:
            result = await self.session.execute(
                select(AgentConfigSnapshot).filter(
                    AgentConfigSnapshot.fingerprint == fingerprint
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving snapshot by fingerprint")
            raise

    async def get_by_agent_id(
        self, agent_id: uuid.UUID
    ) -> list[AgentConfigSnapshotData]:
        """Retrieve all snapshots for an agent, ordered by first_seen_at DESC."""
        try:
            result = await self.session.execute(
                select(AgentConfigSnapshot)
                .filter(AgentConfigSnapshot.agent_id == agent_id)
                .order_by(AgentConfigSnapshot.first_seen_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing snapshots by agent ID")
            raise
