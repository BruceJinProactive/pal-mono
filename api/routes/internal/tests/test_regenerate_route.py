"""Tests for the regenerate_executions route handler."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from api.routes.internal.routines import regenerate_executions
from api.schemas.operations.routine import RegenerateExecutionsResponse

_BASE = "api.routes.internal.routines"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegenerateRoute:
    """Cover the route handler try/except branches (lines 222-251)."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        schedule_id = uuid.uuid4()
        expected = RegenerateExecutionsResponse(
            schedule_id=schedule_id,
            executions_updated=1,
            executions_deleted=2,
            executions_created=3,
        )

        with patch(
            f"{_BASE}.routine_execution_service.regenerate_executions",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            session = AsyncMock()
            result = await regenerate_executions(schedule_id, session)

        assert result.schedule_id == schedule_id
        assert result.executions_updated == 1

    @pytest.mark.asyncio
    async def test_http_exception_reraised(self) -> None:
        """HTTPException from service (404/422) is re-raised, not wrapped in 500."""
        with patch(
            f"{_BASE}.routine_execution_service.regenerate_executions",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=404, detail="not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await regenerate_executions(uuid.uuid4(), AsyncMock())

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_returns_500(self) -> None:
        with patch(
            f"{_BASE}.routine_execution_service.regenerate_executions",
            new_callable=AsyncMock,
            side_effect=SQLAlchemyError("db boom"),
        ):
            session = AsyncMock()
            with pytest.raises(HTTPException) as exc_info:
                await regenerate_executions(uuid.uuid4(), session)

        assert exc_info.value.status_code == 500
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generic_exception_returns_500(self) -> None:
        with patch(
            f"{_BASE}.routine_execution_service.regenerate_executions",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            session = AsyncMock()
            with pytest.raises(HTTPException) as exc_info:
                await regenerate_executions(uuid.uuid4(), session)

        assert exc_info.value.status_code == 500
        session.rollback.assert_awaited_once()
