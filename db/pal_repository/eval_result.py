from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.eval_result import EvalResultData
from db.tables.eval_results import EvalResult
from utils.log import logger


def _thaw(value: Any) -> Any:
    """Recursively convert frozen containers back to JSON-serializable types."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(v) for v in value]
    return value


def _to_data(row: EvalResult) -> EvalResultData:
    """Convert an ORM EvalResult to an EvalResultData."""
    return EvalResultData(
        id=row.id,
        eval_run_id=row.eval_run_id,
        scenario_id=row.scenario_id,
        metric_name=row.metric_name,
        score=row.score,
        passed=row.passed,
        evaluated_at=row.evaluated_at,
        conversation_id=row.conversation_id,
        agent_fingerprint=row.agent_fingerprint,
        reason=row.reason,
        raw_output=row.raw_output,
    )


class EvalResultRepository:
    """Async-only repository for EvalResult records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_run_id(self, eval_run_id: uuid.UUID) -> list[EvalResultData]:
        """Retrieve all eval results for a given eval run."""
        try:
            result = await self.session.execute(
                select(EvalResult)
                .filter(EvalResult.eval_run_id == eval_run_id)
                .order_by(EvalResult.evaluated_at.asc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error getting eval results by run ID")
            raise

    async def get_by_scenario(
        self, eval_run_id: uuid.UUID, scenario_id: str
    ) -> list[EvalResultData]:
        """Retrieve all metric rows for a specific scenario."""
        try:
            result = await self.session.execute(
                select(EvalResult).filter(
                    EvalResult.eval_run_id == eval_run_id,
                    EvalResult.scenario_id == scenario_id,
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error getting eval results by scenario")
            raise

    async def create(self, record: EvalResultData) -> EvalResultData:
        """Create a new eval result."""
        try:
            row = EvalResult(
                id=record.id,
                eval_run_id=record.eval_run_id,
                scenario_id=record.scenario_id,
                metric_name=record.metric_name,
                score=record.score,
                passed=record.passed,
                evaluated_at=record.evaluated_at,
                conversation_id=record.conversation_id,
                agent_fingerprint=record.agent_fingerprint,
                reason=record.reason,
                raw_output=(
                    _thaw(record.raw_output) if record.raw_output is not None else None
                ),
            )
            self.session.add(row)
            await self.session.flush()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating eval result")
            raise
