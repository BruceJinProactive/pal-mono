"""Agent Config Snapshot Repository.

Provides async database operations for agent config snapshots.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from db.tables import AgentConfigSnapshot
from utils.log import logger


class AgentConfigSnapshotRepositoryAsync:
    """Async repository for agent config snapshot operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self, snapshot: AgentConfigSnapshot
    ) -> tuple[AgentConfigSnapshot, bool]:
        """
        Upsert an agent config snapshot by fingerprint (content-addressed PK).

        If the fingerprint already exists, updates last_seen_at to now() and
        returns the existing row with created=False. If it is a new fingerprint,
        inserts the row and returns created=True.

        Args:
            snapshot: AgentConfigSnapshot object to insert or update.

        Returns:
            Tuple of (snapshot, created) where created is True on insert.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            insert_values = {
                "fingerprint": snapshot.fingerprint,
                "agent_id": snapshot.agent_id,
                "project_id": snapshot.project_id,
                "system_prompt_hash": snapshot.system_prompt_hash,
                "system_prompt_text": snapshot.system_prompt_text,
                "config_snapshot": snapshot.config_snapshot,
            }

            stmt = (
                pg_insert(AgentConfigSnapshot)
                .values(**insert_values)
                .on_conflict_do_update(
                    index_elements=["fingerprint"],
                    set_={"last_seen_at": func.now()},
                )
                .returning(
                    AgentConfigSnapshot,
                    # xmax == 0 means the row was freshly inserted (no prior version)
                    AgentConfigSnapshot.__table__.c.fingerprint,
                )
            )

            result = await self.session.execute(stmt)
            row = result.scalar_one()

            await self.session.flush()
            await self.session.refresh(row)

            # Detect insert vs update: on insert first_seen_at == last_seen_at
            # (both set by server default now()); on conflict the explicit
            # func.now() in set_ updates last_seen_at so they diverge.
            created = row.first_seen_at == row.last_seen_at
            return row, created
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error upserting agent config snapshot: {e}")
            raise

    async def get_by_fingerprint(self, fingerprint: str) -> AgentConfigSnapshot | None:
        """
        Retrieve an agent config snapshot by its fingerprint.

        Args:
            fingerprint: SHA-256 hex fingerprint string.

        Returns:
            AgentConfigSnapshot if found, None otherwise.
        """
        try:
            query = select(AgentConfigSnapshot).filter(
                AgentConfigSnapshot.fingerprint == fingerprint
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting agent config snapshot by fingerprint: {e}")
            return None

    async def get_by_agent_id(self, agent_id: uuid.UUID) -> list[AgentConfigSnapshot]:
        """
        Retrieve all agent config snapshots for a given agent.

        Args:
            agent_id: UUID of the agent.

        Returns:
            List of AgentConfigSnapshot objects ordered by first_seen_at DESC.
        """
        try:
            query = (
                select(AgentConfigSnapshot)
                .filter(AgentConfigSnapshot.agent_id == agent_id)
                .order_by(AgentConfigSnapshot.first_seen_at.desc())
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting agent config snapshots by agent_id: {e}")
            return []
