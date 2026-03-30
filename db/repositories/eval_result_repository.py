"""Eval Result Repository.

Provides async database operations for eval results.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import EvalResult
from utils.log import logger


class EvalResultRepositoryAsync:
    """Async repository for eval result operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, result: EvalResult) -> EvalResult:
        """
        Create a new eval result.

        Args:
            result: EvalResult object to create.

        Returns:
            The created EvalResult object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(result)
            await self.session.flush()
            await self.session.refresh(result)
            return result
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating eval result: {e}")
            raise

    async def create_batch(self, results: Sequence[EvalResult]) -> list[EvalResult]:
        """
        Create multiple eval results in a single batch.

        Args:
            results: List of EvalResult objects to create.

        Returns:
            The list of created EvalResult objects with refreshed state.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        if not results:
            return []
        try:
            self.session.add_all(results)
            await self.session.flush()
            for r in results:
                await self.session.refresh(r)
            return list(results)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating eval results in batch: {e}")
            raise

    async def get_by_run_id(self, eval_run_id: uuid.UUID) -> list[EvalResult]:
        """
        Retrieve all eval results for a given eval run.

        Args:
            eval_run_id: UUID of the eval run.

        Returns:
            List of EvalResult objects ordered by evaluated_at ascending,
            or an empty list on error.
        """
        try:
            query = (
                select(EvalResult)
                .filter(EvalResult.eval_run_id == eval_run_id)
                .order_by(EvalResult.evaluated_at.asc())
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting eval results by run id: {e}")
            return []

    async def get_by_scenario(
        self, eval_run_id: uuid.UUID, scenario_id: str
    ) -> list[EvalResult]:
        """
        Retrieve all metric rows for a specific scenario within an eval run.

        Args:
            eval_run_id: UUID of the eval run.
            scenario_id: Identifier of the scenario.

        Returns:
            List of EvalResult objects for the scenario, or an empty list on error.
        """
        try:
            query = select(EvalResult).filter(
                EvalResult.eval_run_id == eval_run_id,
                EvalResult.scenario_id == scenario_id,
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting eval results by scenario: {e}")
            return []
